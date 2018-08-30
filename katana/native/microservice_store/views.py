from django.shortcuts import render
from django.template.loader import render_to_string
from django.http import HttpResponse, JsonResponse
from django.http import StreamingHttpResponse

import os
import json
import subprocess

from utils.navigator_util import Navigator
from utils.command_options_utils import DockerRunCommandOptions

DEFAULT_DATA = {
    "docker_options": {},
    "kubernetes_options": [],
    "host": {
        "address": "localhost",
        "port": "22",
        "username": "arch",
        "password": "arch",
        "end_prompt": "[arch@arch]$"
    },
    "registry": {
        "address": "index.docker.io",
        "image": ""
    }
}

WARRIOR_DIR = Navigator().get_warrior_dir()
PLUGINSPACE_DIR = os.path.join(WARRIOR_DIR, "plugins", "microservice_store_plugin", "pluginspace")
PLUGINSPACE_WDF_DIR = os.path.join(PLUGINSPACE_DIR, "data")
PLUGINSPACE_TC_DIR = os.path.join(PLUGINSPACE_DIR, "testcases")
PLUGINSPACE_TS_DIR = os.path.join(PLUGINSPACE_DIR, "suites")
PLUGINSPACE_TD_VC_DIR = os.path.join(PLUGINSPACE_DIR, "config_files")

WARRIOR_EXE = os.path.join(WARRIOR_DIR, 'Warrior')



# Create your views here.
def index(request):
    """
    Renders landing page of the App
    :param request:
    :return:
    """
    try:
        docker_options = DockerRunCommandOptions(cmd="docker run --help", start="Options:", end=None).get_options_json()
    except Exception as ex:
        print(ex)
        docker_options = {}
    context = DEFAULT_DATA.copy()
    context["docker_options"] = docker_options
    template = "microservice_store/index.html"
    return render(request, template, context)


def generate_host_system_data(host):
    """
    Takes host data, device on which microservice is deployed,
    and generates Input Data File from a template
    :param host:
    :return:
    """
    df = render_to_string("xml_templates/WDF_microservices_host_system_data_template.xml", {"host": host})
    open(os.path.join(PLUGINSPACE_WDF_DIR, "WDF_microservices_host_system_data.xml"), "w+").write(df)
    return


def generate_registry_operations(data):
    """
    Takes host and registry information, and generates
    variable config file from a template
    :param data:
    :return:
    """
    df = render_to_string("xml_templates/VC_microservices_registry_operations_template.xml", {"data": data})
    open(os.path.join(PLUGINSPACE_TD_VC_DIR, "VC_microservices_registry_operations.xml"), "w+").write(df)
    return


def get_dir_path(request):
    directory = os.path.dirname(os.path.abspath(__file__)) + os.sep + '.data'
    return JsonResponse({'data': directory}, safe=False)


def deploy(request):
    """
    Takes request from the browser, makes call to generate
        1. Input Data File
        2. Variable Config File
    and return StreamHTTP back to client, invoking a stream
    function as an yield
    :param request:
    :return:
    """
    data = json.loads(request.GET.get("data"))
    host = data["host"]

    if host["deployment_environment"] == "docker":
        f = "TC_microservices_host_docker_operations.xml"
    elif host["deployment_environment"] == "kubernetes":
        f = "TC_microservices_host_kubernetes_operations.xml"

    generate_host_system_data(data["host"])
    data["registry"]["just_image"] = data["registry"]["image"].split(":")[0].strip()
    generate_registry_operations(data)

    return StreamingHttpResponse(stream(f))


def save(request):
    """
    Takes request from the browser, saves settings to a file
    :param request:
    :return:
    """
    directory = ""
    filename = "settings.dat"
    data = request.POST.get("data")
    data = json.loads(data)
    if "file" in data:
        directory = data["file"].get('directory', '')
        filename = data["file"].get('filename', filename)
    file = os.path.join(directory, filename)
    response = {'status': True, 'file': file}
    try:
        with open(file, 'w') as fd:
            json.dump(data, fd)
    except Exception:
        response['status'] = False
    return JsonResponse(response)


def load(request):
    """
    Takes request from the browser, loads settings from a file
    :param request:
    :return:
    """
    template = "microservice_store/index.html"
    try:
        docker_options = DockerRunCommandOptions(cmd="docker run --help", start="Options:", end=None)
    except Exception as ex:
        docker_options = {}
    context = DEFAULT_DATA.copy()
    context["docker_options"] = docker_options.get_options_json()
    file = request.POST.get("data")

    response = HttpResponse(status=400)
    try:
        with open(file) as fd:
            data = json.load(fd)
            context.update(data)
            response = render(request, template, context)
    except OSError:
        pass
    return response


def stream(file_list):
    """
    Takes TC or TS, and executes warrior, and yields
    response to StreamHTTP
    :param file_list:
    :return:
    """
    f = os.path.join(PLUGINSPACE_TC_DIR, file_list)
    warrior_cmd = '{0} {1} {2}'.format("python3", WARRIOR_EXE, f)
    output = subprocess.Popen(str(warrior_cmd), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               universal_newlines=True)

    print_cmd = '{0} {1} {2}'.format("python3", WARRIOR_EXE, f)

    first_poll = True

    file_li_string = "<li>{0}</li>".format(file_list)

    file_list_html = "<ol>{0}</ol>".format(file_li_string)
    cmd_string = "<h6><strong>Command: </strong></h6>{0}<br>".format(print_cmd)
    logs_heading = "<br><h6><strong>Logs</strong>:</h6>"
    init_string = "<br><h6><strong>Executing:</strong></h6>{0}" \
                       .format(file_list_html) + cmd_string + logs_heading

    while output.poll() is None:
        line = output.stdout.readline()
        if first_poll:
            line = init_string + line
            first_poll = False
            # Yield this line to be used by streaming http response
        yield line + '</br>'
        if line.startswith('-I- DONE'):
            break
    return