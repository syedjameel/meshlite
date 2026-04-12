"""Explicit list of operation modules for PyInstaller frozen bundles.

``pkgutil.walk_packages`` can't discover submodules in a frozen bundle
because the filesystem doesn't exist. This manifest is imported by
:meth:`OperationRegistry.discover` when ``sys.frozen`` is set, so every
operation is still registered.
"""

ALL_OP_MODULES = [
    "meshlite.ops.io.load_mesh",
    "meshlite.ops.io.save_mesh",
    "meshlite.ops.repair.fill_holes",
    "meshlite.ops.repair.auto_repair",
    "meshlite.ops.repair.remove_duplicates",
    "meshlite.ops.simplify.decimate",
    "meshlite.ops.simplify.remesh",
    "meshlite.ops.simplify.subdivide",
    "meshlite.ops.smooth.laplacian",
    "meshlite.ops.transform.translate",
    "meshlite.ops.transform.rotate",
    "meshlite.ops.transform.scale",
    "meshlite.ops.transform.mirror",
    "meshlite.ops.boolean.boolean_op",
    "meshlite.ops.inspect.find_self_intersections",
]
