#!/usr/bin/env python3
import os
import xml.etree.ElementTree as ET
from collections import defaultdict
import argparse
from urllib.request import urlopen
import json
import urllib.parse

from git import Repo

from mvn_dep_updater.data.dependency import Dependency
from mvn_dep_updater.data.project import Project
import base64


# def get_last_version_from_apache_archiva(projects, hostName, idPassword, repoId):
#     idPassword = base64.b64encode(bytes(idPassword,'utf-8'))
#     data = 'Basic '+idPassword.decode('ascii')
#     header = {'Authorization': data}
#     header['Referer'] = hostName
#     header['Content-Type'] = 'application/json'
#     projectNameMapLastVersionFromApi = {}
#
#     for i in projects.keys():
#         if projects[i].group_id != None :
#             url2 = hostName+'restServices/archivaServices/browseService/versionsList/'+projects[i].group_id+'/' + i + '/?repositoryId='+repoId
#             urlVersions = urllib.request.Request(url2, headers=header)
#             readVersions = urllib.request.urlopen(urlVersions)
#             versionData = json.load(readVersions)
#             versions = versionData.get('versions')
#             if len(versions) > 0:
#                 projectNameMapLastVersionFromApi[i] = versions[-1]
#             else:
#                 projectNameMapLastVersionFromApi[i] = None
#     return projectNameMapLastVersionFromApi


def get_last_version_from_apache_archiva(project, hostName, idPassword, repoId):
    idPassword = base64.b64encode(bytes(idPassword,'utf-8'))
    data = 'Basic '+idPassword.decode('ascii')
    header = {'Authorization': data}
    header['Referer'] = hostName
    header['Content-Type'] = 'application/json'

    if project.group_id != None :
        url2 = hostName+'restServices/archivaServices/browseService/versionsList/'+project.group_id+'/' + project.project_id + '/?repositoryId='+repoId
        urlVersions = urllib.request.Request(url2, headers=header)
        readVersions = urllib.request.urlopen(urlVersions)
        versionData = json.load(readVersions)
        versions = versionData.get('versions')
        if len(versions) > 0:
            return versions[-1] # last version
        else:
            return None




def search_for_project_path(path):
    projects = {}

    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith("pom.xml"):
                namespaces = {'xmlns': 'http://maven.apache.org/POM/4.0.0'}
                tree = ET.parse(os.path.join(root, file))
                current_root = tree.getroot()
                project_path = None
                project_artifact_id = None
                project_version = None
                parent_groupId = None
                #find and set parent project id
                if current_root.find("xmlns:groupId", namespaces=namespaces)!=None:
                    parent_groupId = current_root.find("xmlns:groupId", namespaces=namespaces).text

                for d in current_root.findall("xmlns:artifactId", namespaces=namespaces):
                    project_artifact_id = d.text
                    project_path = os.path.join(root, file)
                    dependency_map = {}

                for parent in current_root.findall(".//xmlns:parent", namespaces=namespaces):
                    parent_name = parent.find(".//xmlns:artifactId", namespaces=namespaces).text
                    parent_version = parent.find(".//xmlns:version", namespaces=namespaces).text
                    parent_groupId = parent.find(".//xmlns:groupId",namespaces=namespaces).text
                    dependency = Dependency(parent_name, '', parent_version, True)
                    dependency_map[parent_name] = dependency

                for xml_dependency in current_root.findall(".//xmlns:dependency", namespaces=namespaces):
                    dependencyArtifactId = xml_dependency.find(".//xmlns:artifactId", namespaces=namespaces).text

                    # TODO: var_value and variable_name will be arranged if a propoert is not used for a version value
                    var_value = None
                    variable_name = None

                    if xml_dependency.find(".//xmlns:version", namespaces=namespaces) is not None:
                        version = xml_dependency.find(".//xmlns:version", namespaces=namespaces).text
                        if version.startswith('${'):
                            variable_name = version[2:(len(version) - 1)]
                            for property in current_root.findall(".//xmlns:properties", namespaces=namespaces):
                                element = property.find(".//xmlns:" + variable_name, namespaces=namespaces)
                                if element is not None:
                                    var_value = element.text
                        else:
                            var_value = version


                    dependency = Dependency(dependencyArtifactId, variable_name, var_value)
                    dependency_map[dependencyArtifactId] = dependency

                for xml_project_version in current_root.findall("xmlns:version", namespaces=namespaces):
                    project_version = xml_project_version.text[:len(xml_project_version.text) - 9]

                project = Project(project_artifact_id, project_version, project_path, dependency_map, parent_groupId)
                projects[project_artifact_id] = project

    for project in projects.values():
        dependency_ids = list(project.dependencies.keys())
        for dependency_id in dependency_ids:
            if dependency_id not in projects.keys():
                del project.dependencies[dependency_id]

    return projects



def is_update_needed(versionInMvnRepo, currentDependencyVersion):
    versionInMvnRepo = [int(i) for i in versionInMvnRepo.split('.')]
    currentDependencyVersion = [int(i) for i in currentDependencyVersion.split('.')]

    minLen = len(versionInMvnRepo) if len(versionInMvnRepo) < len(currentDependencyVersion) else len(currentDependencyVersion)

    for i in range(minLen):
        if (currentDependencyVersion[i] > versionInMvnRepo[i]):
            return False
        elif currentDependencyVersion[i] < versionInMvnRepo[i]:
            return True
    if len(currentDependencyVersion) > len(versionInMvnRepo):
        for minLen in range(len(currentDependencyVersion)):
            if currentDependencyVersion[i] != 0:
                return False
    else:
        if len(currentDependencyVersion) == len(versionInMvnRepo):
            return False
    return True



def update_projects(projects, updatingList, hostName, token, repoId):
    for toBeUpdatedProject in updatingList: #type(updaterProject ---> Project)
        print('Checking: ' + toBeUpdatedProject.project_id)
        for dependency in toBeUpdatedProject.dependencies.values():
            print('\tDependency: ' + dependency.id)
            dependencyProject = projects[dependency.id]
            dependencyLatestVersion = get_last_version_from_apache_archiva(dependencyProject, hostName, token, repoId)
            namespaces = {'xmlns': 'http://maven.apache.org/POM/4.0.0'}
            pomTree = ET.parse(toBeUpdatedProject.path)
            roots = pomTree.getroot()
            # check if dependency is parent or not
            # version = ""
            if is_update_needed(dependencyLatestVersion, dependency.version):
                print('\t\tUpdate found=> Current Version: ' + dependency.version + '\t  /\tIn Repo Version: ' + dependencyLatestVersion)
                element = None
                if dependency.isParent:
                        for parent_dependency in roots.findall(".//xmlns:parent", namespaces=namespaces):
                            element = parent_dependency.find(".//xmlns:version", namespaces=namespaces)
                else:
                    if dependency.var_name is not None:
                        for property in roots.findall(".//xmlns:properties", namespaces=namespaces):
                            element = property.find(".//xmlns:" + dependency.var_name, namespaces=namespaces)
                    else:
                        # version =  dependency.version
                        # TODO: Needs fix for none property dependency version values in here
                        pass
                if element is not None:
                    element.text = dependencyLatestVersion
                    ET.register_namespace('', "http://maven.apache.org/POM/4.0.0")
                    pomTree.write(toBeUpdatedProject.path, xml_declaration=True, encoding='utf-8', method='xml')

                update_project_and_deploy(toBeUpdatedProject)


def build_dependency_tree(projects):
    for project in projects.values():
        for dependency in project.dependencies.values():
            for sub_dependency in projects[dependency.id].dependencies.values():
                dependency.add_dependency(sub_dependency)



def print_projects(projects):
    for project in projects.values():
        print("Id: "+project.project_id)
        print("Version: "+project.project_version)
        print("Path: "+ project.path)
        for dependency in project.dependencies.values():
            print("------- dependency: " + dependency.dependecy_id + " ----dependency version: " + dependency.dependecy_version)


def set_level_of_projects(projects, dependency, level):
    if (level > projects[dependency.id].level):
        projects[dependency.id].level = level
    if len(dependency.dependencies.values()) == 0:
        return
    else:
        for sub_dependency in dependency.dependencies.values():
            set_level_of_projects(projects, sub_dependency, level + 1)


def create_update_list(projects):
    for project in projects.values():
        for dependency in project.dependencies.values():
            set_level_of_projects(projects, dependency, 1)
    updatingList = sorted(projects.values(),key=lambda kv : kv.level,reverse=True)
    return updatingList


def job(path, hostName, token, repoId):
    os.chdir(path)

    projects = search_for_project_path(path)

    build_dependency_tree(projects)

    orderedUpdateList = create_update_list(projects)

    # projectNameMapLastVersionFromApi = get_last_version_from_apache_archiva(projects, hostName, token, repoId)

    update_projects(projects, orderedUpdateList, hostName, token, repoId)


def update_project_and_deploy(project):

    #     os.chdir("D:\projects\maven-dependency-updater")
    #     repo = Repo("D:\projects\maven-dependency-updater")
    #     repo.git.checkout('master')
    #     repo.git.add( 'pom.xml')
    #     repo.git.commit('-m', 'Testing')
    #     repo.git.pull('yerel-yedek', 'master')
    #     namespaces = {'xmlns': 'http://maven.apache.org/POM/4.0.0'}
    #     tree = ET.parse('pom.xml')
    #     roots = tree.getroot()
    #     for d in roots.findall("xmlns:artifactId", namespaces=namespaces):
    #         for project in projectsWithFeature:
    #             if project.projectName == d.text:
    #                 a = roots.find("xmlns:version", namespaces=namespaces).text
    #                 if isClientVersionCompatible(a[:len(a) - 9], project.projectVersion):
    # #                     project.projectVersion = a[:len(a) - 9]
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--dir', dest='path', help='Directory if app is used without current working direcotry', required=False)
    parser.add_argument('-H', '--hostname', dest='hostname', help='Hostname or IP address of gitlab with port ex: 192.168.1.2:8080', required=True)
    parser.add_argument('-a', '--aidPw', dest='idPw', help='Apache Archiva authorization in form of user:password', required=True)
    parser.add_argument('-r', '--repoId', dest='repoId', help='Apache Archiva access repository id.', required=True)
    result = parser.parse_args()


    if result is not None:
        path = os.getcwd()
        if result.path is not None:
            path = result.path
        job(path, result.hostname, result.idPw, result.repoId)


if __name__ == "__main__":
    main()
