"""
Support for custom structures in client and server
We only support a subset of features but should be enough
for custom structures
"""

import re
import uuid
import logging
# The next two imports are for generated code
from datetime import datetime
from enum import Enum, IntEnum, EnumMeta
from lxml import objectify

from asyncua import ua

_logger = logging.getLogger(__name__)


def get_default_value(uatype, enums):
    if uatype == "String":
        return "None"
    elif uatype == "Guid":
        return "uuid.uuid4()"
    elif uatype in ("ByteString", "CharArray", "Char"):
        return b''
    elif uatype == "Boolean":
        return "True"
    elif uatype == "DateTime":
        return "datetime.utcnow()"
    elif uatype in ("Int16", "Int32", "Int64", "UInt16", "UInt32", "UInt64", "Double", "Float", "Byte", "SByte"):
        return 0
    elif uatype in enums:
        return f"ua.{uatype}({enums[uatype]})"
    elif hasattr(ua, uatype) and issubclass(getattr(ua, uatype), Enum):
        # We have an enum, try to initilize it correctly
        val = list(getattr(ua, uatype).__members__)[0]
        return f"ua.{uatype}.{val}"
    else:
        return f"ua.{uatype}()"


class EnumType(object):
    def __init__(self, name):
        self.name = name
        self.fields = []
        self.typeid = None

    def get_code(self):
        code = """

class {0}(IntEnum):

    '''
    {0} EnumInt autogenerated from xml
    '''

""".format(self.name)

        for EnumeratedValue in self.fields:
            name = EnumeratedValue.Name
            value = EnumeratedValue.Value
            code += f"    {name} = {value}\n"

        return code


class EnumeratedValue(object):
    def __init__(self, name, value):
        if name == "None":
            name = "None_"
        name = name.replace(" ", "")
        self.Name = name
        self.Value = value


class Struct(object):
    def __init__(self, name):
        self.name = _clean_name(name)
        self.fields = []
        self.typeid = None

    def __str__(self):
        return f"Struct(name={self.name}, fields={self.fields}"
    __repr__ = __str__

    def get_code(self):
        code = f"""

class {self.name}(object):

    '''
    {self.name} structure autogenerated from xml
    '''

"""
        code += '    ua_types = [\n'
        for field in self.fields:
            prefix = 'ListOf' if field.array else ''
            uatype = prefix + field.uatype
            if uatype == 'ListOfChar':
                uatype = 'String'
            code += f"        ('{field.name}', '{uatype}'),\n"
        code += "    ]"
        code += """
    def __str__(self):
        vals = [name + ": " + str(val) for name, val in self.__dict__.items()]
        return self.__class__.__name__ + "(" + ", ".join(vals) + ")"

    __repr__ = __str__

    def __init__(self):
"""
        if not self.fields:
            code += "      pass"
        for field in self.fields:
            code += f"        self.{field.name} = {field.value}\n"
        return code


class Field(object):
    def __init__(self, name):
        self.name = name
        self.uatype = None
        self.value = None
        self.array = False

    def __str__(self):
        return f"Field(name={self.name}, uatype={self.uatype}"
    __repr__ = __str__


class StructGenerator(object):
    def __init__(self):
        self.model = []

    def make_model_from_string(self, xml):
        obj = objectify.fromstring(xml)
        self._make_model(obj)

    def make_model_from_file(self, path):
        obj = objectify.parse(path)
        root = obj.getroot()
        self._make_model(root)

    def _make_model(self, root):
        enums = {}
        for child in root.iter("{*}EnumeratedType"):
            intenum = EnumType(child.get("Name"))
            for xmlfield in child.iter("{*}EnumeratedValue"):
                name = xmlfield.get("Name")
                value = xmlfield.get("Value")
                enumvalue = EnumeratedValue(name, value)
                intenum.fields.append(enumvalue)
                enums[child.get("Name")] = value
            self.model.append(intenum)

        for child in root.iter("{*}StructuredType"):
            struct = Struct(child.get("Name"))
            array = False
            for xmlfield in child.iter("{*}Field"):
                name = xmlfield.get("Name")
                if name.startswith("NoOf"):
                    array = True
                    continue
                field = Field(_clean_name(name))
                field.uatype = xmlfield.get("TypeName")
                if ":" in field.uatype:
                    field.uatype = field.uatype.split(":")[1]
                field.uatype = _clean_name(field.uatype)
                field.value = get_default_value(field.uatype, enums)
                if array:
                    field.array = True
                    field.value = []
                    array = False
                struct.fields.append(field)
            self.model.append(struct)

    def save_to_file(self, path, register=False):
        _file = open(path, "w+")
        self._make_header(_file)
        for struct in self.model:
            _file.write(struct.get_code())
        if register:
            _file.write(self._make_registration())
        _file.close()

    def _make_registration(self):
        code = "\n\n"
        for struct in self.model:
            code += f"ua.register_extension_object('{struct.name}'," \
                    f" ua.NodeId.from_string('{struct.typeid}'), {struct.name})\n"
        return code

    def get_python_classes(self, env=None):
        return _generate_python_class(self.model, env=env)

    def _make_header(self, _file):
        _file.write("""
'''
THIS FILE IS AUTOGENERATED, DO NOT EDIT!!!
'''

from datetime import datetime
import uuid

from asyncua import ua
""")

    def set_typeid(self, name, typeid):
        for struct in self.model:
            if struct.name == name:
                struct.typeid = typeid
                return


async def load_type_definitions(server, nodes=None):
    """
    Download xml from given variable node defining custom structures.
    If no node is given, attemps to import variables from all nodes under
    "0:OPC Binary"
    the code is generated and imported on the fly. If you know the structures
    are not going to be modified it might be interresting to copy the generated files
    and include them in you code
    """
    if nodes is None:
        nodes = []
        for desc in await server.nodes.opc_binary.get_children_descriptions():
            if desc.BrowseName != ua.QualifiedName("Opc.Ua"):
                nodes.append(server.get_node(desc.NodeId))

    structs_dict = {}
    generators = []
    for node in nodes:
        xml = await node.read_value()
        generator = StructGenerator()
        generators.append(generator)
        generator.make_model_from_string(xml)
        # generate and execute new code on the fly
        generator.get_python_classes(structs_dict)
        # same but using a file that is imported. This can be usefull for debugging library
        # name = node.read_browse_name().Name
        # Make sure structure names do not contain charaters that cannot be used in Python class file names
        # name = _clean_name(name)
        # name = "structures_" + node.read_browse_name().Name
        # generator.save_and_import(name + ".py", append_to=structs_dict)

        # register classes
        # every children of our node should represent a class
        for ndesc in await node.get_children_descriptions():
            ndesc_node = server.get_node(ndesc.NodeId)
            ref_desc_list = await ndesc_node.get_references(refs=ua.ObjectIds.HasDescription,
                                                            direction=ua.BrowseDirection.Inverse)
            if ref_desc_list:  # some server put extra things here
                name = _clean_name(ndesc.BrowseName.Name)
                if name not in structs_dict:
                    _logger.warning("%s is found as child of binary definition node but is not found in xml", name)
                    continue
                nodeid = ref_desc_list[0].NodeId
                ua.register_extension_object(name, nodeid, structs_dict[name])
                # save the typeid if user want to create static file for type definitnion
                generator.set_typeid(name, nodeid.to_string())

        for key, val in structs_dict.items():
            if isinstance(val, EnumMeta) and key != "IntEnum":
                setattr(ua, key, val)

    return generators, structs_dict


def _clean_name(name):
    """
    Remove characters that might be present in  OPC UA structures
    but cannot be part of of Python class names
    """
    name = re.sub(r'\W+', '_', name)
    name = re.sub(r'^[0-9]+', r'_\g<0>', name)

    return name


def _generate_python_class(model, env=None):
    """
    generate Python code and execute in a new environment
    return a dict of structures {name: class}
    Rmw: Since the code is generated on the fly, in case of error the stack trace is
    not available and debugging is very hard...
    """
    if env is None:
        env = {}
    #  Add the required libraries to dict
    if "ua" not in env:
        env['ua'] = ua
    if "datetime" not in env:
        env['datetime'] = datetime
    if "uuid" not in env:
        env['uuid'] = uuid
    if "enum" not in env:
        env['IntEnum'] = IntEnum
    # generate classes one by one and add them to dict
    for element in model:
        code = element.get_code()
        exec(code, env)
    return env


async def load_enums(server, env=None):
    """
    Read enumeration data types on server and generate python Enums in ua scope for them
    """
    model = []
    nodes = await server.nodes.enum_data_type.get_children()
    if env is None:
        env = ua.__dict__
    for node in nodes:
        name = (await node.read_browse_name()).Name
        try:
            c = await _get_enum_strings(name, node)
        except ua.UaError as ex:
            try:
                c = await _get_enum_values(name, node)
            except ua.UaError as ex:
                _logger.warning(f"Node {name}, {node} under DataTypes/Enumeration,"
                                f" does not seem to have a child called EnumString or EumValue: {ex}")
                continue
        if not hasattr(ua, c.name):
            _logger.warning("Adding enum %s to ua namespace", c)
            model.append(c)
    return _generate_python_class(model, env=env)


async def _get_enum_values(name, node):
    def_node = await node.get_child("0:EnumValues")
    val = await def_node.read_value()
    c = EnumType(name)
    c.fields = [EnumeratedValue(enumval.DisplayName.Text, enumval.Value) for enumval in val]
    return c


async def _get_enum_strings(name, node):
    def_node = await node.get_child("0:EnumStrings")
    val = await def_node.read_value()
    c = EnumType(name)
    c.fields = [EnumeratedValue(st.Text, idx) for idx, st in enumerate(val)]
    return c
