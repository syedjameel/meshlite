"""M5 — OperationRegistry + ParamSchema tests."""

from __future__ import annotations

import pytest

from meshlite.ops import (
    Operation,
    OperationRegistry,
    Param,
    ParamSchema,
    register_operation,
)

# ---------------------------------------------------------------------------
# Registry isolation: each test that mutates the registry restores it after.
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_registry():
    """Snapshot the registry before the test and restore it after."""
    snapshot = dict(OperationRegistry._ops)
    OperationRegistry.clear()
    yield
    OperationRegistry.clear()
    OperationRegistry._ops.update(snapshot)


# ---------------------------------------------------------------------------
# Param + ParamSchema
# ---------------------------------------------------------------------------

def test_param_schema_defaults() -> None:
    schema = ParamSchema(
        (
            Param("a", "float", "A", default=1.5),
            Param("b", "int", "B", default=3),
            Param("c", "bool", "C", default=True),
            Param("d", "enum", "D", default="x", choices=("x", "y", "z")),
        )
    )
    assert schema.defaults() == {"a": 1.5, "b": 3, "c": True, "d": "x"}
    assert len(schema) == 4
    assert schema.by_name("c").label == "C"
    assert schema.by_name("missing") is None


def test_param_schema_validate_fills_defaults() -> None:
    schema = ParamSchema(
        (
            Param("a", "float", "A", default=1.0),
            Param("b", "int", "B", default=2),
        )
    )
    out = schema.validate({"a": 9.0})
    assert out == {"a": 9.0, "b": 2}


def test_param_schema_validate_unknown_key_raises() -> None:
    schema = ParamSchema((Param("a", "float", "A", default=1.0),))
    with pytest.raises(ValueError, match="unknown param"):
        schema.validate({"bogus": 1})


def test_param_schema_validate_numeric_bounds() -> None:
    schema = ParamSchema(
        (Param("a", "float", "A", default=0.5, min=0.0, max=1.0),)
    )
    schema.validate({"a": 0.5})         # ok
    schema.validate({"a": 0.0})         # boundary ok
    schema.validate({"a": 1.0})         # boundary ok
    with pytest.raises(ValueError, match="below min"):
        schema.validate({"a": -0.1})
    with pytest.raises(ValueError, match="above max"):
        schema.validate({"a": 1.1})


def test_param_schema_validate_enum_choice() -> None:
    schema = ParamSchema(
        (Param("m", "enum", "M", default="x", choices=("x", "y", "z")),)
    )
    schema.validate({"m": "y"})
    with pytest.raises(ValueError, match="not in choices"):
        schema.validate({"m": "q"})


# ---------------------------------------------------------------------------
# Registry: register / get / by_category
# ---------------------------------------------------------------------------

def test_register_decorator(isolated_registry) -> None:
    @register_operation
    class FooOp(Operation):
        id = "test.foo"
        label = "Foo"
        category = "Test"

        def run(self, mesh, params, ctx):
            pass

    assert OperationRegistry.has("test.foo")
    assert OperationRegistry.get("test.foo") is FooOp
    assert OperationRegistry["test.foo"] is FooOp                # subscript sugar
    assert FooOp in OperationRegistry.all()


def test_register_duplicate_id_raises(isolated_registry) -> None:
    @register_operation
    class A(Operation):
        id = "test.dup"
        label = "A"

        def run(self, mesh, params, ctx):
            pass

    with pytest.raises(ValueError, match="duplicate"):
        @register_operation
        class B(Operation):                                       # noqa: F811
            id = "test.dup"
            label = "B"

            def run(self, mesh, params, ctx):
                pass


def test_register_empty_id_raises(isolated_registry) -> None:
    class NoId(Operation):
        label = "No id"

        def run(self, mesh, params, ctx):
            pass

    # ``id`` is a ClassVar without a default — accessing it directly raises
    # AttributeError, so register() trips its `not hasattr` guard.
    with pytest.raises(ValueError, match="non-empty class-level"):
        OperationRegistry.register(NoId)


def test_get_unknown_raises(isolated_registry) -> None:
    with pytest.raises(KeyError):
        OperationRegistry.get("nope")


def test_by_category_groups_and_sorts(isolated_registry) -> None:
    @register_operation
    class A(Operation):
        id = "x.a"
        label = "Apple"
        category = "Fruit"

        def run(self, mesh, params, ctx):
            pass

    @register_operation
    class B(Operation):
        id = "x.b"
        label = "Banana"
        category = "Fruit"

        def run(self, mesh, params, ctx):
            pass

    @register_operation
    class C(Operation):
        id = "x.c"
        label = "Carrot"
        category = "Veg"

        def run(self, mesh, params, ctx):
            pass

    grouped = OperationRegistry.by_category()
    assert set(grouped.keys()) == {"Fruit", "Veg"}
    assert [c.label for c in grouped["Fruit"]] == ["Apple", "Banana"]
    assert [c.label for c in grouped["Veg"]] == ["Carrot"]


# ---------------------------------------------------------------------------
# Auto-discovery
# ---------------------------------------------------------------------------

def test_discover_finds_io_ops(isolated_registry) -> None:
    """``discover()`` should pick up the io.load_mesh and io.save_mesh modules."""
    n = OperationRegistry.discover()
    assert n >= 2
    assert OperationRegistry.has("io.load_mesh")
    assert OperationRegistry.has("io.save_mesh")
    # The dev counter op lives under ops/_dev/ which discover() skips.
    assert not OperationRegistry.has("_dev.counter")
