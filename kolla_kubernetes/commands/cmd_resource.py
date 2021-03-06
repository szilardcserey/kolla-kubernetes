# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function
import sys

from oslo_log import log

from kolla_kubernetes.commands.base_command import KollaKubernetesBaseCommand
from kolla_kubernetes.service_resources import KollaKubernetesResources
from kolla_kubernetes.service_resources import Service
from kolla_kubernetes.utils import FileUtils
from kolla_kubernetes.utils import JinjaUtils
from kolla_kubernetes.utils import YamlUtils

LOG = log.getLogger(__name__)
KKR = KollaKubernetesResources.Get()


class Resource(KollaKubernetesBaseCommand):
    """Create, delete, or query status for kolla-kubernetes resources"""

    def get_parser(self, prog_name):
        parser = super(Resource, self).get_parser(prog_name)
        parser.add_argument(
            "action",
            metavar="<action>",
            help=("One of [%s]" % ("|".join(Service.VALID_ACTIONS)))
        )
        parser.add_argument(
            "service_name",
            metavar="<service-name>",
            help=("One of [%s]" % ("|".join(KKR.getServices().keys())))
        )
        parser.add_argument(
            "resource_type",
            metavar="<resource-type>",
            help=("One of [%s]" % ("|".join(Service.VALID_RESOURCE_TYPES)))
        )
        return parser

    def take_action(self, args):
        self.validate_args(args)
        service = KKR.getServiceByName(args.service_name)
        service.do_apply(args.action, args.resource_type)

    def validate_args(self, args):
        if args.action not in Service.VALID_ACTIONS:
            msg = ("action [{}] not in valid actions [{}]".format(
                args.action,
                "|".join(Service.VALID_ACTIONS)))
            raise Exception(msg)
        if args.service_name not in KKR.getServices().keys():
            msg = ("service_name [{}] not in valid service_names [{}]".format(
                args.service_name,
                "|".join(KKR.getServices().keys())))
            raise Exception(msg)
        if args.resource_type not in Service.VALID_RESOURCE_TYPES:
            msg = ("resource_type [{}] not in valid resource_types [{}]"
                   .format(args.resource_type,
                           "|".join(Service.VALID_RESOURCE_TYPES)))
            raise Exception(msg)

        service = KKR.getServiceByName(args.service_name)
        if (args.resource_type != 'configmap') and (
            len(service.getResourceTemplatesByType(args.resource_type)) == 0):
            msg = ("service_name [{}] has no resource"
                   " files defined for type [{}]".format(
                       args.service_name, args.resource_type))
            raise Exception(msg)


class ResourceTemplate(Resource):
    """Jinja process kolla-kubernetes resource template files"""

    # This command adds the CLI params as part of the Jinja vars for processing
    # templates. This is needed because some of the templates will need to know
    # the arguments with which this CLI is called.  For example, some
    # resource-type "disk" templates may reference '{{
    # kolla_kubernetes.cli.args.action }}' to produce output such as "gcloud
    # disk create" or "gcloud disk delete" based on the CLI params.  Most
    # templates will not require this, but it is needed for some.

    def get_parser(self, prog_name):
        parser = super(ResourceTemplate, self).get_parser(prog_name)
        parser.add_argument(
            "resource_name",
            metavar="<resource-name>",
            help=("The unique resource-name under service->resource_type")
        )
        parser.add_argument(
            '--print-jinja-vars',
            action='store_true',
            help=("If this boolean is set, the final jinja vars dict used as"
                  " input for template processing will be printed to stderr.  "
                  " The vars dict is created by merging configuration files "
                  " from several sources before applying the dict to itself.")
        ),
        parser.add_argument(
            '--print-jinja-keys-regex',
            metavar='<print-jinja-keys-regex>',
            type=str,
            default=None,
            help=("If this regex string is set, all matching keys encountered"
                  " during the creation of the jinja vars dict will be printed"
                  " to stderr at each stage of processing.  The vars dict is"
                  " created by merging configuration files from several"
                  " sources before applying the dict to itself.")
        )
        return parser

    def take_action(self, args):
        # Validate input arguments
        self.validate_args(args)
        if args.resource_type == 'configmap':
            msg = ("resource-template subcommand for resource-type {} "
                   "is not yet supported".format(args.resource_type))
            raise Exception(msg)

        service = KKR.getServiceByName(args.service_name)
        rt = service.getResourceTemplateByTypeAndName(
            args.resource_type, args.resource_name)

        variables = KKR.GetJinjaDict(service.getName(), vars(args),
                                     args.print_jinja_keys_regex)

        # Merge the template vars with the jinja vars before processing
        variables['kolla_kubernetes'].update(
            {"template": {"vars": rt.getVars()}})

        # handle the debug option --print-jinja-vars
        if args.print_jinja_vars is True:
            print(YamlUtils.yaml_dict_to_string(variables), file=sys.stderr)

        # process the template
        print(JinjaUtils.render_jinja(
            variables,
            FileUtils.read_string_from_file(rt.getTemplatePath())))


class ResourceMap(KollaKubernetesBaseCommand):
    """List available kolla-kubernetes resources to be created or deleted"""

    # If the operator has any question on what Services have what resources,
    # and what resources reference which resourcefiles (on disk), then this
    # command is helpful.  This command prints the available resources in a
    # tree of Service->ResourceType->ResourceFiles.

    def get_parser(self, prog_name):
        parser = super(ResourceMap, self).get_parser(prog_name)
        parser.add_argument(
            "--resource-type",
            metavar="<resource-type>",
            help=("Filter by one of [%s]" % (
                "|".join(Service.VALID_RESOURCE_TYPES)))
        )
        parser.add_argument(
            "--service-name",
            metavar="<service-name>",
            help=("Filter by one of [%s]" % (
                "|".join(KKR.getServices().keys())))
        )
        return parser

    def take_action(self, args):
        for service_name, s in KKR.getServices().items():

            # Skip specific services if the user has defined a filter
            if (args.service_name is not None) and (
                    args.service_name != service_name):
                continue

            print('service[{}]'.format(s.getName()))

            for t in Service.VALID_RESOURCE_TYPES:
                # Skip specific resource_types if the user has defined a filter
                if args.resource_type is not None and args.resource_type != t:
                    continue

                # Skip special case configmaps, which are not defined in the
                #   config file but instead are loaded from searching the kolla
                #   configs.
                if t == 'configmap':
                    continue

                resourceTemplates = s.getResourceTemplatesByType(t)

                print('  resource_type[{}] num_items[{}]'.format(
                    t, len(resourceTemplates)))

                # Print the resource files
                for rt in s.getResourceTemplatesByType(t):
                    print('    ' + str(rt))
