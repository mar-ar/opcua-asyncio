# encoding: utf-8

"""
Tests that will be run twice. Once on server side and once on
client side since we have been carefull to have the exact
same api on server and client side
"""

import asyncio
from datetime import datetime
from datetime import timedelta
import math

import pytest

from asyncua import ua, uamethod, Node
from asyncua.common import ua_utils
from asyncua.common.methods import call_method_full
from asyncua.common.copy_node_util import copy_node
from asyncua.common.instantiate_util import instantiate

pytestmark = pytest.mark.asyncio


async def add_server_methods(srv):
    @uamethod
    def func(parent, value):
        return value * 2

    o = srv.get_objects_node()
    await o.add_method(
        ua.NodeId("ServerMethod", 2), ua.QualifiedName('ServerMethod', 2),
        func, [ua.VariantType.Int64], [ua.VariantType.Int64]
    )

    @uamethod
    def func2(parent, methodname, value):
        if methodname == "panic":
            return ua.StatusCode(ua.StatusCodes.BadOutOfMemory)
        if methodname != "sin":
            res = ua.CallMethodResult()
            res.StatusCode = ua.StatusCode(ua.StatusCodes.BadInvalidArgument)
            res.InputArgumentResults = [ua.StatusCode(ua.StatusCodes.BadNotSupported), ua.StatusCode()]
            return res
        return math.sin(value)

    o = srv.get_objects_node()
    await o.add_method(
        ua.NodeId("ServerMethodArray", 2), ua.QualifiedName('ServerMethodArray', 2), func2,
        [ua.VariantType.String, ua.VariantType.Int64], [ua.VariantType.Int64]
    )

    @uamethod
    def func3(parent, mylist):
        return [i * 2 for i in mylist]

    o = srv.get_objects_node()
    await o.add_method(
        ua.NodeId("ServerMethodArray2", 2), ua.QualifiedName('ServerMethodArray2', 2), func3,
        [ua.VariantType.Int64], [ua.VariantType.Int64]
    )

    @uamethod
    def func4(parent):
        return None

    base_otype = srv.get_node(ua.ObjectIds.BaseObjectType)
    custom_otype = await base_otype.add_object_type(2, 'ObjectWithMethodsType')
    await custom_otype.add_method(2, 'ServerMethodDefault', func4)
    await (await custom_otype.add_method(2, 'ServerMethodMandatory', func4)).set_modelling_rule(True)
    await (await custom_otype.add_method(2, 'ServerMethodOptional', func4)).set_modelling_rule(False)
    await (await custom_otype.add_method(2, 'ServerMethodNone', func4)).set_modelling_rule(None)
    await o.add_object(2, 'ObjectWithMethods', custom_otype)

    @uamethod
    def func5(parent):
        return 1, 2, 3

    o = srv.get_objects_node()
    await o.add_method(
        ua.NodeId("ServerMethodTuple", 2), ua.QualifiedName('ServerMethodTuple', 2), func5, [],
        [ua.VariantType.Int64, ua.VariantType.Int64, ua.VariantType.Int64]
    )

    @uamethod
    async def func6(parent):
        await asyncio.sleep(0)

    o = srv.get_objects_node()
    await o.add_method(
        ua.NodeId("ServerMethodAsync", 2), ua.QualifiedName('ServerMethodAsync', 2), func6, [], []
    )


async def test_find_servers(opc):
    servers = await opc.opc.find_servers()
    # FIXME : finish


async def test_add_node_bad_args(opc):
    obj = opc.opc.get_objects_node()

    with pytest.raises(TypeError):
        fold = await obj.add_folder(1.2, "kk")

    with pytest.raises(TypeError):
        fold = await obj.add_folder(ua.UaError, "khjh")

    with pytest.raises(ua.UaError):
        fold = await obj.add_folder("kjk", 1.2)

    with pytest.raises(TypeError):
        fold = await obj.add_folder("i=0;s='oooo'", 1.2)

    with pytest.raises(ua.UaError):
        fold = await obj.add_folder("i=0;s='oooo'", "tt:oioi")


async def test_delete_nodes(opc):
    obj = opc.opc.get_objects_node()
    fold = await obj.add_folder(2, "FolderToDelete")
    var = await fold.add_variable(2, "VarToDelete", 9.1)
    childs = await fold.get_children()
    assert var in childs
    await opc.opc.delete_nodes([var])
    with pytest.raises(ua.UaStatusCodeError):
        await var.set_value(7.8)
    with pytest.raises(ua.UaStatusCodeError):
        await obj.get_child(["2:FolderToDelete", "2:VarToDelete"])
    childs = await fold.get_children()
    assert var not in childs


async def test_delete_nodes_recursive(opc):
    obj = opc.opc.get_objects_node()
    fold = await obj.add_folder(2, "FolderToDeleteR")
    var = await fold.add_variable(2, "VarToDeleteR", 9.1)
    await opc.opc.delete_nodes([fold, var])
    with pytest.raises(ua.UaStatusCodeError):
        await var.set_value(7.8)
    with pytest.raises(ua.UaStatusCodeError):
        await obj.get_child(["2:FolderToDelete", "2:VarToDelete"])


async def test_delete_nodes_recursive2(opc):
    obj = opc.opc.get_objects_node()
    fold = await obj.add_folder(2, "FolderToDeleteRoot")
    nfold = fold
    mynodes = []
    for i in range(7):
        nfold = await fold.add_folder(2, "FolderToDeleteRoot")
        var = await fold.add_variable(2, "VarToDeleteR", 9.1)
        var = await fold.add_property(2, "ProToDeleteR", 9.1)
        prop = await fold.add_property(2, "ProToDeleteR", 9.1)
        o = await fold.add_object(3, "ObjToDeleteR")
        mynodes.append(nfold)
        mynodes.append(var)
        mynodes.append(prop)
        mynodes.append(o)
    await opc.opc.delete_nodes([fold], recursive=True)
    for node in mynodes:
        with pytest.raises(ua.UaStatusCodeError):
            await node.get_browse_name()


async def test_delete_references(opc):
    newtype = await opc.opc.get_node(ua.ObjectIds.HierarchicalReferences).add_reference_type(0, "HasSuperSecretVariable")

    obj = opc.opc.get_objects_node()
    fold = await obj.add_folder(2, "FolderToRef")
    var = await fold.add_variable(2, "VarToRef", 42)

    await fold.add_reference(var, newtype)

    assert [fold] == await var.get_referenced_nodes(newtype)
    assert [var] == await fold.get_referenced_nodes(newtype)

    await fold.delete_reference(var, newtype)

    assert [] == await var.get_referenced_nodes(newtype)
    assert [] == await fold.get_referenced_nodes(newtype)

    await fold.add_reference(var, newtype, bidirectional=False)

    assert [] == await var.get_referenced_nodes(newtype)
    assert [var] == await fold.get_referenced_nodes(newtype)

    await fold.delete_reference(var, newtype)

    assert [] == await var.get_referenced_nodes(newtype)
    assert [] == await fold.get_referenced_nodes(newtype)

    await var.add_reference(fold, newtype, forward=False, bidirectional=False)

    assert [fold] == await var.get_referenced_nodes(newtype)
    assert [] == await fold.get_referenced_nodes(newtype)

    with pytest.raises(ua.UaStatusCodeError):
        await fold.delete_reference(var, newtype)

    assert [fold] == await var.get_referenced_nodes(newtype)
    assert [] == await fold.get_referenced_nodes(newtype)

    with pytest.raises(ua.UaStatusCodeError):
        await var.delete_reference(fold, newtype)

    assert [fold] == await var.get_referenced_nodes(newtype)
    assert [] == await fold.get_referenced_nodes(newtype)

    await var.delete_reference(fold, newtype, forward=False)

    assert [] == await var.get_referenced_nodes(newtype)
    assert [] == await fold.get_referenced_nodes(newtype)

    # clean-up
    await opc.opc.delete_nodes([fold, newtype], recursive=True)


async def test_server_node(opc):
    node = opc.opc.get_server_node()
    assert ua.QualifiedName('Server', 0) == await node.get_browse_name()


async def test_root(opc):
    root = opc.opc.get_root_node()
    assert ua.QualifiedName('Root', 0) == await root.get_browse_name()
    assert ua.LocalizedText('Root') == await root.get_display_name()
    nid = ua.NodeId(84, 0)
    assert nid == root.nodeid


async def test_objects(opc):
    objects = opc.opc.get_objects_node()
    assert ua.QualifiedName('Objects', 0) == await objects.get_browse_name()
    nid = ua.NodeId(85, 0)
    assert nid == objects.nodeid


async def test_browse(opc):
    objects = opc.opc.get_objects_node()
    obj = await objects.add_object(4, "browsetest")
    folder = await obj.add_folder(4, "folder")
    prop = await obj.add_property(4, "property", 1)
    prop2 = await obj.add_property(4, "property2", 2)
    var = await obj.add_variable(4, "variable", 3)
    obj2 = await obj.add_object(4, "obj")
    alle = await obj.get_children()
    assert prop in alle
    assert prop2 in alle
    assert var in alle
    assert folder in alle
    assert obj not in alle
    props = await obj.get_children(refs=ua.ObjectIds.HasProperty)
    assert prop in props
    assert prop2 in props
    assert var not in props
    assert folder not in props
    assert obj2 not in props
    all_vars = await obj.get_children(nodeclassmask=ua.NodeClass.Variable)
    assert prop in all_vars
    assert var in all_vars
    assert folder not in props
    assert obj2 not in props
    all_objs = await obj.get_children(nodeclassmask=ua.NodeClass.Object)
    assert folder in all_objs
    assert obj2 in all_objs
    assert var not in all_objs


async def test_browse_references(opc):
    objects = opc.opc.get_objects_node()
    folder = await objects.add_folder(4, "folder")

    childs = await objects.get_referenced_nodes(
        refs=ua.ObjectIds.Organizes, direction=ua.BrowseDirection.Forward, includesubtypes=False
    )
    assert folder in childs

    childs = await objects.get_referenced_nodes(
        refs=ua.ObjectIds.Organizes, direction=ua.BrowseDirection.Both, includesubtypes=False
    )
    assert folder in childs

    childs = await objects.get_referenced_nodes(
        refs=ua.ObjectIds.Organizes, direction=ua.BrowseDirection.Inverse, includesubtypes=False
    )
    assert folder not in childs

    parents = await folder.get_referenced_nodes(
        refs=ua.ObjectIds.Organizes, direction=ua.BrowseDirection.Inverse, includesubtypes=False
    )
    assert objects in parents

    parents = await folder.get_referenced_nodes(
        refs=ua.ObjectIds.HierarchicalReferences, direction=ua.BrowseDirection.Inverse, includesubtypes=False
    )
    assert objects in parents
    assert await folder.get_parent() == objects


async def test_browsename_with_spaces(opc):
    o = opc.opc.get_objects_node()
    v = await o.add_variable(3, 'BNVariable with spaces and %&+?/', 1.3)
    v2 = await o.get_child("3:BNVariable with spaces and %&+?/")
    assert v == v2


async def test_non_existing_path(opc):
    root = opc.opc.get_root_node()
    with pytest.raises(ua.UaStatusCodeError):
        await root.get_child(['0:Objects', '0:Server', '0:nonexistingnode'])


async def test_bad_attribute(opc):
    root = opc.opc.get_root_node()
    with pytest.raises(ua.UaStatusCodeError):
        await root.set_value(99)


async def test_get_node_by_nodeid(opc):
    root = opc.opc.get_root_node()
    server_time_node = await root.get_child(['0:Objects', '0:Server', '0:ServerStatus', '0:CurrentTime'])
    correct = opc.opc.get_node(ua.NodeId(ua.ObjectIds.Server_ServerStatus_CurrentTime))
    assert server_time_node == correct


async def test_datetime_read(opc):
    time_node = opc.opc.get_node(ua.NodeId(ua.ObjectIds.Server_ServerStatus_CurrentTime))
    dt = await time_node.get_value()
    utcnow = datetime.utcnow()
    delta = utcnow - dt
    assert delta < timedelta(seconds=1)


async def test_datetime_write(opc):
    time_node = opc.opc.get_node(ua.NodeId(ua.ObjectIds.Server_ServerStatus_CurrentTime))
    now = datetime.utcnow()
    objects = opc.opc.get_objects_node()
    v1 = await objects.add_variable(4, "test_datetime", now)
    tid = await v1.get_value()
    assert now == tid


async def test_variant_array_dim(opc):
    objects = opc.opc.get_objects_node()
    l = [[[1.0, 1.0, 1.0, 1.0], [2.0, 2.0, 2.0, 2.0], [3.0, 3.0, 3.0, 3.0]],
        [[5.0, 5.0, 5.0, 5.0], [7.0, 8.0, 9.0, 01.0], [1.0, 1.0, 1.0, 1.0]]]
    v = await objects.add_variable(3, 'variableWithDims', l)

    await v.set_array_dimensions([0, 0, 0])
    dim = await v.get_array_dimensions()
    assert [0, 0, 0] == dim

    await v.set_value_rank(0)
    rank = await v.get_value_rank()
    assert 0 == rank

    v2 = await v.get_value()
    assert l == v2
    dv = await v.get_data_value()
    assert [2, 3, 4] == dv.Value.Dimensions

    l = [[[], [], []], [[], [], []]]
    variant = ua.Variant(l, ua.VariantType.UInt32)
    v = await objects.add_variable(3, 'variableWithDimsEmpty', variant)
    v2 = await v.get_value()
    assert l == v2
    dv = await v.get_data_value()
    assert [2, 3, 0] == dv.Value.Dimensions


async def test_add_numeric_variable(opc):
    objects = opc.opc.get_objects_node()
    v = await objects.add_variable('ns=3;i=888;', '3:numericnodefromstring', 99)
    nid = ua.NodeId(888, 3)
    qn = ua.QualifiedName('numericnodefromstring', 3)
    assert nid == v.nodeid
    assert qn == await v.get_browse_name()


async def test_add_string_variable(opc):
    objects = opc.opc.get_objects_node()
    v = await objects.add_variable('ns=3;s=stringid;', '3:stringnodefromstring', [68])
    nid = ua.NodeId('stringid', 3)
    qn = ua.QualifiedName('stringnodefromstring', 3)
    assert nid == v.nodeid
    assert qn == await v.get_browse_name()


async def test_utf8(opc):
    objects = opc.opc.get_objects_node()
    utf_string = "æøå@%&"
    bn = ua.QualifiedName(utf_string, 3)
    nid = ua.NodeId("æølå", 3)
    val = "æøå"
    v = await objects.add_variable(nid, bn, val)
    assert nid == v.nodeid
    val2 = await v.get_value()
    assert val == val2
    bn2 = await v.get_browse_name()
    assert bn == bn2


async def test_null_variable(opc):
    objects = opc.opc.get_objects_node()
    var = await objects.add_variable(3, 'nullstring', "a string")
    await var.set_value(None)
    val = await var.get_value()
    assert val is None
    await var.set_value("")
    val = await var.get_value()
    assert val is not None
    assert "" == val


async def test_variable_data_type(opc):
    objects = opc.opc.get_objects_node()
    var = await objects.add_variable(3, 'stringfordatatype', "a string")
    val = await var.get_data_type_as_variant_type()
    assert ua.VariantType.String == val
    var = await objects.add_variable(3, 'stringarrayfordatatype', ["a", "b"])
    val = await var.get_data_type_as_variant_type()
    assert ua.VariantType.String == val


async def test_add_string_array_variable(opc):
    objects = opc.opc.get_objects_node()
    v = await objects.add_variable('ns=3;s=stringarrayid;', '9:stringarray', ['l', 'b'])
    nid = ua.NodeId('stringarrayid', 3)
    qn = ua.QualifiedName('stringarray', 9)
    assert nid == v.nodeid
    assert qn == await v.get_browse_name()
    val = await v.get_value()
    assert ['l', 'b'] == val


async def test_add_numeric_node(opc):
    objects = opc.opc.get_objects_node()
    nid = ua.NodeId(9999, 3)
    qn = ua.QualifiedName('AddNodeVar1', 3)
    v1 = await objects.add_variable(nid, qn, 0)
    assert nid == v1.nodeid
    assert qn == await v1.get_browse_name()


async def test_add_string_node(opc):
    objects = opc.opc.get_objects_node()
    qn = ua.QualifiedName('AddNodeVar2', 3)
    nid = ua.NodeId('AddNodeVar2Id', 3)
    v2 = await objects.add_variable(nid, qn, 0)
    assert nid == v2.nodeid
    assert qn == await v2.get_browse_name()


async def test_add_find_node_(opc):
    objects = opc.opc.get_objects_node()
    o = await objects.add_object('ns=2;i=101;', '2:AddFindObject')
    o2 = await objects.get_child('2:AddFindObject')
    assert o == o2


async def test_node_path(opc):
    objects = opc.opc.get_objects_node()
    o = await objects.add_object('ns=2;i=105;', '2:NodePathObject')
    root = opc.opc.get_root_node()
    o2 = await root.get_child(['0:Objects', '2:NodePathObject'])
    assert o == o2


async def test_add_read_node(opc):
    objects = opc.opc.get_objects_node()
    o = await objects.add_object('ns=2;i=102;', '2:AddReadObject')
    nid = ua.NodeId(102, 2)
    assert nid == o.nodeid
    qn = ua.QualifiedName('AddReadObject', 2)
    assert qn == await o.get_browse_name()


async def test_simple_value(opc):
    o = opc.opc.get_objects_node()
    v = await o.add_variable(3, 'VariableTestValue', 4.32)
    val = await v.get_value()
    assert 4.32 == val


async def test_add_exception(opc):
    objects = opc.opc.get_objects_node()
    await objects.add_object('ns=2;i=103;', '2:AddReadObject')
    with pytest.raises(ua.UaStatusCodeError):
        await objects.add_object('ns=2;i=103;', '2:AddReadObject')


async def test_negative_value(opc):
    o = opc.opc.get_objects_node()
    v = await o.add_variable(3, 'VariableNegativeValue', 4)
    await v.set_value(-4.54)
    assert -4.54 == await v.get_value()


async def test_read_server_state(opc):
    statenode = opc.opc.get_node(ua.NodeId(ua.ObjectIds.Server_ServerStatus_State))
    assert 0 == await statenode.get_value()


async def test_bad_node(opc):
    bad = opc.opc.get_node(ua.NodeId(999, 999))
    with pytest.raises(ua.UaStatusCodeError):
        await bad.get_browse_name()
    with pytest.raises(ua.UaStatusCodeError):
        await bad.set_value(89)
    with pytest.raises(ua.UaStatusCodeError):
        await bad.add_object(0, "0:myobj")
    with pytest.raises(ua.UaStatusCodeError):
        await bad.get_child("0:myobj")


async def test_value(opc):
    o = opc.opc.get_objects_node()
    var = ua.Variant(1.98, ua.VariantType.Double)
    v = await o.add_variable(3, 'VariableValue', var)
    assert 1.98 == await v.get_value()
    dvar = ua.DataValue(var)
    dv = await v.get_data_value()
    assert ua.DataValue == type(dv)
    assert dvar.Value == dv.Value
    assert dvar.Value == var


async def test_set_value(opc):
    o = opc.opc.get_objects_node()
    var = ua.Variant(1.98, ua.VariantType.Double)
    dvar = ua.DataValue(var)
    v = await o.add_variable(3, 'VariableValue', var)
    await v.set_value(var.Value)
    v1 = await v.get_value()
    assert v1 == var.Value
    await v.set_value(var)
    v2 = await v.get_value()
    assert v2 == var.Value
    await v.set_data_value(dvar)
    v3 = await v.get_data_value()
    assert v3.Value == dvar.Value


async def test_array_value(opc):
    o = opc.opc.get_objects_node()
    v = await o.add_variable(3, 'VariableArrayValue', [1, 2, 3])
    assert [1, 2, 3] == await v.get_value()


async def test_bool_variable(opc):
    o = opc.opc.get_objects_node()
    v = await o.add_variable(3, 'BoolVariable', True)
    dt = await v.get_data_type_as_variant_type()
    assert ua.VariantType.Boolean == dt
    val = await v.get_value()
    assert val is True
    await v.set_value(False)
    val = await v.get_value()
    assert val is False


async def test_array_size_one_value(opc):
    o = opc.opc.get_objects_node()
    v = await o.add_variable(3, 'VariableArrayValue', [1, 2, 3])
    await v.set_value([1])
    assert [1] == await v.get_value()


async def test_use_namespace(opc):
    idx = await opc.opc.get_namespace_index("urn:freeopcua:python:server")
    assert 1 == idx
    root = opc.opc.get_root_node()
    myvar = await root.add_variable(idx, 'var_in_custom_namespace', [5])
    myid = myvar.nodeid
    assert idx == myid.NamespaceIndex


async def test_method(opc):
    o = opc.opc.get_objects_node()
    await o.get_child("2:ServerMethod")
    result = await o.call_method("2:ServerMethod", 2.1)
    assert 4.2 == result
    with pytest.raises(ua.UaStatusCodeError):
        # FIXME: we should raise a more precise exception
        await o.call_method("2:ServerMethod", 2.1, 89, 9)
    with pytest.raises(ua.UaStatusCodeError):
        await o.call_method(ua.NodeId(999), 2.1)  # non existing method


async def test_method_array(opc):
    o = opc.opc.get_objects_node()
    m = await o.get_child("2:ServerMethodArray")
    result = await o.call_method(m, "sin", ua.Variant(math.pi))
    assert result < 0.01
    with pytest.raises(ua.UaStatusCodeError) as exc_info:
        await o.call_method(m, "cos", ua.Variant(math.pi))
    assert ua.StatusCodes.BadInvalidArgument == exc_info.type.code
    with pytest.raises(ua.UaStatusCodeError) as exc_info:
        await o.call_method(m, "panic", ua.Variant(math.pi))
    assert ua.StatusCodes.BadOutOfMemory == exc_info.type.code


async def test_method_array2(opc):
    o = opc.opc.get_objects_node()
    m = await o.get_child("2:ServerMethodArray2")
    result = await o.call_method(m, [1.1, 3.4, 9])
    assert [2.2, 6.8, 18] == result
    result = await call_method_full(o, m, [1.1, 3.4, 9])
    assert [[2.2, 6.8, 18]] == result.OutputArguments


async def test_method_tuple(opc):
    o = opc.opc.get_objects_node()
    m = await o.get_child("2:ServerMethodTuple")
    result = await o.call_method(m)
    assert [1, 2, 3] == result
    result = await call_method_full(o, m)
    assert [1, 2, 3] == result.OutputArguments


async def test_method_none(opc):
    # this test calls the function linked to the type's method..
    o = await opc.opc.get_node(ua.ObjectIds.BaseObjectType).get_child("2:ObjectWithMethodsType")
    m = await o.get_child("2:ServerMethodDefault")
    result = await o.call_method(m)
    assert result is None
    result = await call_method_full(o, m)
    assert [] == result.OutputArguments


async def test_method_async(opc):
    o = opc.opc.get_objects_node()
    m = await o.get_child("2:ServerMethodAsync")
    await o.call_method(m)
    await call_method_full(o, m)


async def test_add_nodes(opc):
    objects = opc.opc.get_objects_node()
    f = await objects.add_folder(3, 'MyFolder')
    child = await objects.get_child("3:MyFolder")
    assert child == f
    o = await f.add_object(3, 'MyObject')
    child = await f.get_child("3:MyObject")
    assert child == o
    v = await f.add_variable(3, 'MyVariable', 6)
    child = await f.get_child("3:MyVariable")
    assert child == v
    p = await f.add_property(3, 'MyProperty', 10)
    child = await f.get_child("3:MyProperty")
    assert child == p
    childs = await f.get_children()
    assert o in childs
    assert v in childs
    assert p in childs


async def test_modelling_rules(opc):
    obj = await opc.opc.nodes.base_object_type.add_object_type(2, 'MyFooObjectType')
    v = await obj.add_variable(2, "myvar", 1.1)
    await v.set_modelling_rule(True)
    p = await obj.add_property(2, "myvar", 1.1)
    await p.set_modelling_rule(False)

    refs = await obj.get_referenced_nodes(refs=ua.ObjectIds.HasModellingRule)
    assert 0 == len(refs)

    refs = await v.get_referenced_nodes(refs=ua.ObjectIds.HasModellingRule)
    assert opc.opc.get_node(ua.ObjectIds.ModellingRule_Mandatory) == refs[0]

    refs = await p.get_referenced_nodes(refs=ua.ObjectIds.HasModellingRule)
    assert opc.opc.get_node(ua.ObjectIds.ModellingRule_Optional) == refs[0]

    await p.set_modelling_rule(None)
    refs = await p.get_referenced_nodes(refs=ua.ObjectIds.HasModellingRule)
    assert 0 == len(refs)


async def test_incl_subtypes(opc):
    base_type = await opc.opc.get_root_node().get_child(["0:Types", "0:ObjectTypes", "0:BaseObjectType"])
    descs = await base_type.get_children_descriptions(includesubtypes=True)
    assert len(descs) > 10
    descs = await base_type.get_children_descriptions(includesubtypes=False)
    assert 0 == len(descs)


async def test_add_node_with_type(opc):
    objects = opc.opc.get_objects_node()
    f = await objects.add_folder(3, 'MyFolder_TypeTest')

    o = await f.add_object(3, 'MyObject1', ua.ObjectIds.BaseObjectType)
    assert ua.ObjectIds.BaseObjectType == (await o.get_type_definition()).Identifier

    o = await f.add_object(3, 'MyObject2', ua.NodeId(ua.ObjectIds.BaseObjectType, 0))
    assert ua.ObjectIds.BaseObjectType == (await o.get_type_definition()).Identifier

    base_otype = opc.opc.get_node(ua.ObjectIds.BaseObjectType)
    custom_otype = await base_otype.add_object_type(2, 'MyFooObjectType')

    o = await f.add_object(3, 'MyObject3', custom_otype.nodeid)
    assert custom_otype.nodeid.Identifier == (await o.get_type_definition()).Identifier

    references = await o.get_references(refs=ua.ObjectIds.HasTypeDefinition, direction=ua.BrowseDirection.Forward)
    assert 1 == len(references)
    assert custom_otype.nodeid == references[0].NodeId


async def test_references_for_added_nodes(opc):
    objects = opc.opc.get_objects_node()
    o = await objects.add_object(3, 'MyObject')
    nodes = await objects.get_referenced_nodes(
        refs=ua.ObjectIds.Organizes, direction=ua.BrowseDirection.Forward, includesubtypes=False
    )
    assert o in nodes
    nodes = await o.get_referenced_nodes(
        refs=ua.ObjectIds.Organizes, direction=ua.BrowseDirection.Inverse, includesubtypes=False
    )
    assert objects in nodes
    assert objects == await o.get_parent()
    assert ua.ObjectIds.BaseObjectType == (await o.get_type_definition()).Identifier
    assert [] == await o.get_references(ua.ObjectIds.HasModellingRule)

    o2 = await o.add_object(3, 'MySecondObject')
    nodes = await o.get_referenced_nodes(
        refs=ua.ObjectIds.HasComponent, direction=ua.BrowseDirection.Forward, includesubtypes=False
    )
    assert o2 in nodes
    nodes = await o2.get_referenced_nodes(
        refs=ua.ObjectIds.HasComponent, direction=ua.BrowseDirection.Inverse, includesubtypes=False
    )
    assert o in nodes
    assert o == await o2.get_parent()
    assert ua.ObjectIds.BaseObjectType == (await o2.get_type_definition()).Identifier
    assert [] == await o2.get_references(ua.ObjectIds.HasModellingRule)

    v = await o.add_variable(3, 'MyVariable', 6)
    nodes = await o.get_referenced_nodes(
        refs=ua.ObjectIds.HasComponent, direction=ua.BrowseDirection.Forward, includesubtypes=False
    )
    assert v in nodes
    nodes = await v.get_referenced_nodes(
        refs=ua.ObjectIds.HasComponent, direction=ua.BrowseDirection.Inverse, includesubtypes=False
    )
    assert o in nodes
    assert o == await v.get_parent()
    assert ua.ObjectIds.BaseDataVariableType == (await v.get_type_definition()).Identifier
    assert [] == await v.get_references(ua.ObjectIds.HasModellingRule)

    p = await o.add_property(3, 'MyProperty', 2)
    nodes = await o.get_referenced_nodes(
        refs=ua.ObjectIds.HasProperty, direction=ua.BrowseDirection.Forward, includesubtypes=False
    )
    assert p in nodes
    nodes = await p.get_referenced_nodes(
        refs=ua.ObjectIds.HasProperty, direction=ua.BrowseDirection.Inverse, includesubtypes=False
    )
    assert o in nodes
    assert o == await p.get_parent()
    assert ua.ObjectIds.PropertyType == (await p.get_type_definition()).Identifier
    assert [] == await p.get_references(ua.ObjectIds.HasModellingRule)

    m = await objects.get_child("2:ServerMethod")
    assert [] == await m.get_references(ua.ObjectIds.HasModellingRule)


async def test_path_string(opc):
    o = await (await opc.opc.nodes.objects.add_folder(1, "titif")).add_object(3, "opath")
    path = await o.get_path(as_string=True)
    assert ["0:Root", "0:Objects", "1:titif", "3:opath"] == path
    path = await o.get_path(2, as_string=True)
    assert ["1:titif", "3:opath"] == path


async def test_path(opc):
    of = await opc.opc.nodes.objects.add_folder(1, "titif")
    op = await of.add_object(3, "opath")
    path = await op.get_path()
    assert [opc.opc.nodes.root, opc.opc.nodes.objects, of, op] == path
    path = await op.get_path(2)
    assert [of, op] == path
    target = opc.opc.get_node("i=13387")
    path = await target.get_path()
    assert [
               opc.opc.nodes.root, opc.opc.nodes.types, opc.opc.nodes.object_types, opc.opc.nodes.base_object_type,
               opc.opc.nodes.folder_type, opc.opc.get_node(ua.ObjectIds.FileDirectoryType), target
           ] == path


async def test_get_endpoints(opc):
    endpoints = await opc.opc.get_endpoints()
    assert len(endpoints) > 0
    assert endpoints[0].EndpointUrl.startswith("opc.tcp://")


async def test_copy_node(opc):
    dev_t = await opc.opc.nodes.base_data_type.add_object_type(0, "MyDevice")
    v_t = await dev_t.add_variable(0, "sensor", 1.0)
    p_t = await dev_t.add_property(0, "sensor_id", "0340")
    ctrl_t = await dev_t.add_object(0, "controller")
    prop_t = await ctrl_t.add_property(0, "state", "Running")
    # Create device sutype
    devd_t = await dev_t.add_object_type(0, "MyDeviceDervived")
    v_t = await devd_t.add_variable(0, "childparam", 1.0)
    p_t = await devd_t.add_property(0, "sensorx_id", "0340")
    nodes = await copy_node(opc.opc.nodes.objects, dev_t)
    mydevice = nodes[0]
    assert ua.NodeClass.ObjectType == await mydevice.get_node_class()
    assert 4 == len(await mydevice.get_children())
    obj = await mydevice.get_child(["0:controller"])
    prop = await mydevice.get_child(["0:controller", "0:state"])
    assert ua.ObjectIds.PropertyType == (await prop.get_type_definition()).Identifier
    assert "Running" == await prop.get_value()
    assert prop.nodeid != prop_t.nodeid


async def test_instantiate_1(opc):
    # Create device type
    dev_t = await opc.opc.nodes.base_object_type.add_object_type(0, "MyDevice")
    v_t = await dev_t.add_variable(0, "sensor", 1.0)
    await v_t.set_modelling_rule(True)
    p_t = await dev_t.add_property(0, "sensor_id", "0340")
    await p_t.set_modelling_rule(True)
    ctrl_t = await dev_t.add_object(0, "controller")
    await ctrl_t.set_modelling_rule(True)
    v_opt_t = await dev_t.add_variable(0, "vendor", 1.0)
    await v_opt_t.set_modelling_rule(False)
    v_none_t = await dev_t.add_variable(0, "model", 1.0)
    await v_none_t.set_modelling_rule(None)
    prop_t = await ctrl_t.add_property(0, "state", "Running")
    await prop_t.set_modelling_rule(True)

    # Create device sutype
    devd_t = await dev_t.add_object_type(0, "MyDeviceDervived")
    v_t = await devd_t.add_variable(0, "childparam", 1.0)
    await v_t.set_modelling_rule(True)
    p_t = await devd_t.add_property(0, "sensorx_id", "0340")
    await p_t.set_modelling_rule(True)

    # instanciate device
    nodes = await instantiate(opc.opc.nodes.objects, dev_t, bname="2:Device0001")
    mydevice = nodes[0]

    assert ua.NodeClass.Object == await mydevice.get_node_class()
    assert dev_t.nodeid == await mydevice.get_type_definition()
    obj = await mydevice.get_child(["0:controller"])
    prop = await mydevice.get_child(["0:controller", "0:state"])
    with pytest.raises(ua.UaError):
        await mydevice.get_child(["0:controller", "0:vendor"])
    with pytest.raises(ua.UaError):
        await mydevice.get_child(["0:controller", "0:model"])

    assert ua.ObjectIds.PropertyType == (await prop.get_type_definition()).Identifier
    assert "Running" == await prop.get_value()
    assert prop.nodeid != prop_t.nodeid

    # instanciate device subtype
    nodes = await instantiate(opc.opc.nodes.objects, devd_t, bname="2:Device0002")
    mydevicederived = nodes[0]
    prop1 = await mydevicederived.get_child(["0:sensorx_id"])
    var1 = await mydevicederived.get_child(["0:childparam"])
    var_parent = await mydevicederived.get_child(["0:sensor"])
    prop_parent = await mydevicederived.get_child(["0:sensor_id"])


async def test_instantiate_string_nodeid(opc):
    # Create device type
    dev_t = await opc.opc.nodes.base_object_type.add_object_type(0, "MyDevice2")
    v_t = await dev_t.add_variable(0, "sensor", 1.0)
    await v_t.set_modelling_rule(True)
    p_t = await dev_t.add_property(0, "sensor_id", "0340")
    await p_t.set_modelling_rule(True)
    ctrl_t = await dev_t.add_object(0, "controller")
    await ctrl_t.set_modelling_rule(True)
    prop_t = await ctrl_t.add_property(0, "state", "Running")
    await prop_t.set_modelling_rule(True)

    # instanciate device
    nodes = await instantiate(opc.opc.nodes.objects, dev_t, nodeid=ua.NodeId("InstDevice", 2, ua.NodeIdType.String),
        bname="2:InstDevice")
    mydevice = nodes[0]

    assert ua.NodeClass.Object == await mydevice.get_node_class()
    assert dev_t.nodeid == await mydevice.get_type_definition()
    obj = await mydevice.get_child(["0:controller"])
    obj_nodeid_ident = obj.nodeid.Identifier
    prop = await mydevice.get_child(["0:controller", "0:state"])
    assert "InstDevice.controller" == obj_nodeid_ident
    assert ua.ObjectIds.PropertyType == (await prop.get_type_definition()).Identifier
    assert "Running" == await prop.get_value()
    assert prop.nodeid != prop_t.nodeid


async def test_variable_with_datatype(opc):
    v1 = await opc.opc.nodes.objects.add_variable(
        3, 'VariableEnumType1', ua.ApplicationType.ClientAndServer, datatype=ua.NodeId(ua.ObjectIds.ApplicationType)
    )
    tp1 = await v1.get_data_type()
    assert tp1 == ua.NodeId(ua.ObjectIds.ApplicationType)

    v2 = await opc.opc.nodes.objects.add_variable(
        3, 'VariableEnumType2', ua.ApplicationType.ClientAndServer, datatype=ua.NodeId(ua.ObjectIds.ApplicationType)
    )
    tp2 = await v2.get_data_type()
    assert tp2 == ua.NodeId(ua.ObjectIds.ApplicationType)


async def test_enum(opc):
    # create enum type
    enums = await opc.opc.get_root_node().get_child(["0:Types", "0:DataTypes", "0:BaseDataType", "0:Enumeration"])
    myenum_type = await enums.add_data_type(0, "MyEnum")
    es = await myenum_type.add_variable(
        0, "EnumStrings", [ua.LocalizedText("String0"), ua.LocalizedText("String1"), ua.LocalizedText("String2")],
        ua.VariantType.LocalizedText
    )
    # es.set_value_rank(1)
    # instantiate
    o = opc.opc.get_objects_node()
    myvar = await o.add_variable(2, "MyEnumVar", ua.LocalizedText("String1"), datatype=myenum_type.nodeid)
    # myvar.set_writable(True)
    # tests
    assert myenum_type.nodeid == await myvar.get_data_type()
    await myvar.set_value(ua.LocalizedText("String2"))


async def test_supertypes(opc):
    nint32 = opc.opc.get_node(ua.ObjectIds.Int32)
    node = await ua_utils.get_node_supertype(nint32)
    assert opc.opc.get_node(ua.ObjectIds.Integer) == node

    nodes = await ua_utils.get_node_supertypes(nint32)
    assert opc.opc.get_node(ua.ObjectIds.Number) == nodes[1]
    assert opc.opc.get_node(ua.ObjectIds.Integer) == nodes[0]

    # test custom
    dtype = await nint32.add_data_type(0, "MyCustomDataType")
    node = await ua_utils.get_node_supertype(dtype)
    assert nint32 == node

    dtype2 = await dtype.add_data_type(0, "MyCustomDataType2")
    node = await ua_utils.get_node_supertype(dtype2)
    assert dtype == node


async def test_base_data_type(opc):
    nint32 = opc.opc.get_node(ua.ObjectIds.Int32)
    dtype = await nint32.add_data_type(0, "MyCustomDataType")
    dtype2 = await dtype.add_data_type(0, "MyCustomDataType2")
    assert nint32 == await ua_utils.get_base_data_type(dtype)
    assert nint32 == await ua_utils.get_base_data_type(dtype2)

    ext = await opc.opc.nodes.objects.add_variable(0, "MyExtensionObject", ua.Argument())
    d = await ext.get_data_type()
    d = opc.opc.get_node(d)
    assert opc.opc.get_node(ua.ObjectIds.Structure) == await ua_utils.get_base_data_type(d)
    assert ua.VariantType.ExtensionObject == await ua_utils.data_type_to_variant_type(d)


async def test_data_type_to_variant_type(opc):
    test_data = {
        ua.ObjectIds.Boolean: ua.VariantType.Boolean,
        ua.ObjectIds.Byte: ua.VariantType.Byte,
        ua.ObjectIds.String: ua.VariantType.String,
        ua.ObjectIds.Int32: ua.VariantType.Int32,
        ua.ObjectIds.UInt32: ua.VariantType.UInt32,
        ua.ObjectIds.NodeId: ua.VariantType.NodeId,
        ua.ObjectIds.LocalizedText: ua.VariantType.LocalizedText,
        ua.ObjectIds.Structure: ua.VariantType.ExtensionObject,
        ua.ObjectIds.EnumValueType: ua.VariantType.ExtensionObject,
        ua.ObjectIds.Enumeration: ua.VariantType.Int32,  # enumeration
        ua.ObjectIds.AttributeWriteMask: ua.VariantType.UInt32,
        ua.ObjectIds.AxisScaleEnumeration: ua.VariantType.Int32  # enumeration
    }
    for dt, vdt in test_data.items():
        assert vdt == await ua_utils.data_type_to_variant_type(opc.opc.get_node(ua.NodeId(dt)))


async def test_guid_node_id():
    """
    Test that a Node can be instantiated with a GUID string and that the NodeId ca be converted to binary.
    """
    node = Node(None, "ns=4;g=35d5f86f-2777-4550-9d48-b098f5ee285c")
    binary_node_id = ua.ua_binary.nodeid_to_binary(node.nodeid)
    assert type(binary_node_id) is bytes
