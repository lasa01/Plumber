from typing import Iterable, Tuple, Optional, List, Dict, Any, Callable
import vmfpy
from os import path
from mathutils import geometry, Vector, Euler, Matrix
from math import inf, radians, floor, ceil, isclose
from itertools import chain, combinations, islice
import bpy
import time
import traceback


# maximum distance to a side plane before cutting a vertice off
_CUT_EPSILON = 0.01


VectorPair = Tuple[Vector, Vector]


def _plane_from_points(p1: vmfpy.VMFVector, p2: vmfpy.VMFVector, p3: vmfpy.VMFVector) -> VectorPair:
    vectors = (Vector(p3), Vector(p2), Vector(p1))
    normal = geometry.normal(vectors)
    return ((vectors[0] + vectors[2]) / 2, normal)


def _intersect_planes(p1: VectorPair, p2: VectorPair, p3: VectorPair) -> Optional[Vector]:
    line: VectorPair = geometry.intersect_plane_plane(*p1, *p2)
    if line[0] is None:
        return None
    return geometry.intersect_line_plane(line[0], line[0] + line[1], *p3)


def _vec_isclose(a: Vector, b: Vector, ref: Vector, rel_tol: float = 1e-6, abs_tol: float = 0.005) -> bool:
    return (isclose(a.x - ref.x, b.x - ref.x, rel_tol=rel_tol, abs_tol=abs_tol)
            and isclose(a.y - ref.y, b.y - ref.y, rel_tol=rel_tol, abs_tol=abs_tol)
            and isclose(a.z - ref.z, b.z - ref.z, rel_tol=rel_tol, abs_tol=abs_tol))


def _tuple_lerp(a: Tuple[float, float], b: Tuple[float, float], amount: float) -> Tuple[float, float]:
    return (a[0] * (1 - amount) + b[0] * amount, a[1] * (1 - amount) + b[1] * amount)


class VMFImporter():
    def __init__(self, data_dirs: Iterable[str], data_paks: Iterable[str], dec_models_path: str = None,
                 import_solids: bool = True, import_overlays: bool = True,
                 import_props: bool = True, import_materials: bool = True, import_lights: bool = True,
                 scale: float = 0.01, epsilon: float = 0.001,
                 light_factor: float = 0.1, sun_factor: float = 0.01, ambient_factor: float = 0.001,
                 verbose: bool = False, skip_tools: bool = False):
        self.epsilon = epsilon
        self.import_solids = import_solids
        self.import_overlays = import_overlays
        self.import_props = import_props
        self.import_materials = import_materials
        self.import_lights = import_lights
        self.light_factor = light_factor
        self.sun_factor = sun_factor
        self.ambient_factor = ambient_factor
        self.scale = scale
        self.verbose = verbose
        self.skip_tools = skip_tools
        self.dec_models_path = "" if dec_models_path is None else dec_models_path
        self._vmf_fs = vmfpy.fs.VMFFileSystem(data_dirs, data_paks, index_files=False)
        self._vmt_importer: Optional['import_vmt.VMTImporter']
        if import_overlays:
            self._side_vertices: Dict[int, List[Vector]] = {}
            self._side_face_vertices: Dict[int, List[List[int]]] = {}
            self._side_normals: Dict[int, Vector] = {}
        if import_materials:
            from . import import_vmt
            self._vmt_importer = import_vmt.VMTImporter(self.verbose)
        else:
            self._vmt_importer = None
        self._fallback_materials: Dict[str, bpy.types.Material] = {}
        # self._mdl_importer = None
        self._qc_importer = None
        if import_props:
            # try:
            #     from . import import_mdl
            #     self._mdl_importer = import_mdl.MDLImporter(self._vmf_fs, self._vmt_importer, self.verbose)
            # except ImportError:
            from . import import_qc
            self._qc_importer = import_qc.QCImporter(
                self.dec_models_path, self._vmf_fs, self._vmt_importer, self.verbose
            )
        self.need_files = import_materials or import_props
        if self.need_files:
            print("Indexing game files...")
            start = time.time()
            self._vmf_fs.index_all()
            print(f"Indexing done in {time.time() - start} s")

    def __enter__(self) -> 'VMFImporter':
        if self._qc_importer is not None:
            self._qc_importer.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        if self._qc_importer is not None:
            self._qc_importer.__exit__(exc_type, exc_value, traceback)

    def load(self, file_path: str, context: bpy.types.Context, data_dir: str = None) -> None:
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        print("Loading VMF...")
        start = time.time()
        if data_dir is not None and self.need_files:
            print("Indexing map files...")
            self._vmf_fs.index_dir(data_dir)
        print("Parsing map...")
        vmf = vmfpy.VMF(open(file_path, encoding="utf-8"), self._vmf_fs)
        success_solids = 0
        failed_solids = 0
        success_overlays = 0
        failed_overlays = 0
        success_props = 0
        failed_props = 0
        success_lights = 0
        failed_lights = 0
        map_collection = bpy.data.collections.new(path.splitext(path.basename(file_path))[0])
        context.collection.children.link(map_collection)
        if self.import_solids:
            print("Building geometry...")
            world_collection = bpy.data.collections.new(vmf.world.classname)
            map_collection.children.link(world_collection)
            for solid in vmf.world.solids:
                try:
                    self._load_solid(solid, vmf.world.classname, world_collection)
                except Exception as err:
                    print(f"ERROR LOADING SOLID: {err}")
                    if self.verbose:
                        traceback.print_exception(type(err), err, err.__traceback__)
                    failed_solids += 1
                else:
                    success_solids += 1
            func_collection = bpy.data.collections.new("func")
            map_collection.children.link(func_collection)
            for func_entity in vmf.func_entities:
                for solid in func_entity.solids:
                    try:
                        self._load_solid(solid, func_entity.classname, func_collection)
                    except Exception as err:
                        print(f"ERROR LOADING SOLID: {err}")
                        if self.verbose:
                            traceback.print_exception(type(err), err, err.__traceback__)
                        failed_solids += 1
                    else:
                        success_solids += 1
        if self.import_overlays:
            print("Importing overlays...")
            collection = bpy.data.collections.new("overlay")
            map_collection.children.link(collection)
            for overlay_entity in vmf.overlay_entities:
                try:
                    self._load_overlay(overlay_entity, collection)
                except Exception as err:
                    print(f"ERROR LOADING OVERLAY: {err}")
                    if self.verbose:
                        traceback.print_exception(type(err), err, err.__traceback__)
                    failed_overlays += 1
                else:
                    success_overlays += 1
        if self.import_props:
            print("Importing props...")
            prop_collection = bpy.data.collections.new("prop")
            map_collection.children.link(prop_collection)
            for prop_entity in vmf.prop_entities:
                try:
                    self._load_prop(prop_entity, prop_collection)
                except Exception as err:
                    print(f"ERROR LOADING PROP: {err}")
                    if self.verbose:
                        traceback.print_exception(type(err), err, err.__traceback__)
                    failed_props += 1
                else:
                    success_props += 1
        if self.import_lights:
            print("Importing lights...")
            light_collection = bpy.data.collections.new("light")
            map_collection.children.link(light_collection)
            if vmf.env_light_entity is not None:
                try:
                    self._load_env_light(vmf.env_light_entity, context, light_collection)
                except Exception as err:
                    print(f"ERROR LOADING ENVIRONMENT LIGHT: {err}")
                    if self.verbose:
                        traceback.print_exception(type(err), err, err.__traceback__)
                    failed_lights += 1
                else:
                    success_lights += 1
            for light_entity in vmf.light_entities:
                try:
                    self._load_light(light_entity, light_collection)
                except Exception as err:
                    print(f"ERROR LOADING LIGHT: {err}")
                    if self.verbose:
                        traceback.print_exception(type(err), err, err.__traceback__)
                    failed_lights += 1
                else:
                    success_lights += 1
            for spotlight_entity in vmf.spot_light_entities:
                try:
                    self._load_spotlight(spotlight_entity, light_collection)
                except Exception as err:
                    print(f"ERROR LOADING SPOTLIGHT: {err}")
                    if self.verbose:
                        traceback.print_exception(type(err), err, err.__traceback__)
                    failed_lights += 1
                else:
                    success_lights += 1

        print(f"Done in {time.time() - start} s")
        if self.import_solids:
            print(f"Imported {success_solids} solids ({failed_solids} failed)")
        if self.import_overlays:
            print(f"Imported {success_overlays} overlays ({failed_overlays}) failed")
        if self.import_props:
            print(f"Imported {success_props} props ({failed_props} failed)")
        if self.import_lights:
            print(f"Imported {success_lights} lights ({failed_lights} failed)")

    def _load_light(self, vmf_light: vmfpy.VMFLightEntity, collection: bpy.types.Collection) -> None:
        name = f"{vmf_light.classname}_{vmf_light.id}"
        light: bpy.types.PointLight = bpy.data.lights.new(name, 'POINT')
        light.cycles.use_multiple_importance_sampling = False
        use_sdr = vmf_light.hdr_color == (-1, -1, -1)
        light.color = [c / 255 for c in vmf_light.color] if use_sdr else [c / 255 for c in vmf_light.hdr_color]
        light.energy = (vmf_light.brightness if use_sdr
                        else vmf_light.hdr_brightness * vmf_light.hdr_scale) * self.light_factor
        # TODO: possible to convert constant-linear-quadratic attenuation into blender?
        obj: bpy.types.Object = bpy.data.objects.new(name, object_data=light)
        collection.objects.link(obj)
        obj.location = (vmf_light.origin.x * self.scale,
                        vmf_light.origin.y * self.scale,
                        vmf_light.origin.z * self.scale)

    def _load_spotlight(self, vmf_light: vmfpy.VMFSpotLightEntity, collection: bpy.types.Collection) -> None:
        name = f"{vmf_light.classname}_{vmf_light.id}"
        light: bpy.types.SpotLight = bpy.data.lights.new(name, 'SPOT')
        light.cycles.use_multiple_importance_sampling = False
        use_sdr = vmf_light.hdr_color == (-1, -1, -1)
        light.color = [c / 255 for c in vmf_light.color] if use_sdr else [c / 255 for c in vmf_light.hdr_color]
        light.energy = (vmf_light.brightness if use_sdr
                        else vmf_light.hdr_brightness * vmf_light.hdr_scale) * self.light_factor
        light.spot_size = radians(vmf_light.cone)
        light.spot_blend = 1 - (vmf_light.inner_cone / 90)  # TODO: more accurate conversion for this
        obj: bpy.types.Object = bpy.data.objects.new(name, object_data=light)
        collection.objects.link(obj)
        obj.location = (vmf_light.origin.x * self.scale,
                        vmf_light.origin.y * self.scale,
                        vmf_light.origin.z * self.scale)
        obj.rotation_euler = Euler((0, radians(-90), 0))
        obj.rotation_euler.rotate(Euler((
            radians(vmf_light.angles[2]),
            radians(-vmf_light.pitch),
            radians(vmf_light.angles[1])
        )))

    def _load_env_light(self, vmf_light: vmfpy.VMFEnvLightEntity,
                        context: bpy.types.Context, collection: bpy.types.Collection) -> None:
        light: bpy.types.SunLight = bpy.data.lights.new(vmf_light.classname, 'SUN')
        light.cycles.use_multiple_importance_sampling = True
        light.angle = radians(vmf_light.sun_spread_angle)
        use_sdr = vmf_light.hdr_color == (-1, -1, -1)
        light.color = [c / 255 for c in vmf_light.color] if use_sdr else [c / 255 for c in vmf_light.hdr_color]
        light.energy = (vmf_light.brightness if use_sdr
                        else vmf_light.hdr_brightness * vmf_light.hdr_scale) * self.sun_factor
        obj: bpy.types.Object = bpy.data.objects.new(vmf_light.classname, object_data=light)
        collection.objects.link(obj)
        obj.location = (vmf_light.origin.x * self.scale,
                        vmf_light.origin.y * self.scale,
                        vmf_light.origin.z * self.scale)
        obj.rotation_euler = Euler((0, radians(-90), 0))
        obj.rotation_euler.rotate(Euler((
            radians(vmf_light.angles[2]),
            radians(-vmf_light.pitch),
            radians(vmf_light.angles[1])
        )))

        context.scene.world.use_nodes = True
        nt = context.scene.world.node_tree
        nt.nodes.clear()
        out_node: bpy.types.Node = nt.nodes.new('ShaderNodeOutputWorld')
        out_node.location = (0, 0)
        bg_node: bpy.types.Node = nt.nodes.new('ShaderNodeBackground')
        bg_node.location = (-300, 0)
        nt.links.new(bg_node.outputs['Background'], out_node.inputs['Surface'])
        use_sdr = vmf_light.amb_hdr_color == (-1, -1, -1)
        bg_node.inputs['Color'].default_value = ([c / 255 for c in vmf_light.amb_color] + [1] if use_sdr
                                                 else [c / 255 for c in vmf_light.amb_hdr_color] + [1])
        bg_node.inputs['Strength'].default_value = (vmf_light.amb_brightness if use_sdr
                                                    else vmf_light.amb_hdr_brightness
                                                    * vmf_light.amb_hdr_scale) * self.ambient_factor

    def _load_material(self, name: str, opener: Callable[[], vmfpy.vmt.VMT]) -> Tuple[int, int, bpy.types.Material]:
        if name in self._fallback_materials:
            return 1, 1, self._fallback_materials[name]
        if self._vmt_importer is not None:
            try:
                return self._vmt_importer.load(name, opener)
            except FileNotFoundError:
                print(f"WARNING: MATERIAL {name} NOT FOUND")
            except vmfpy.vmt.VMTParseException as err:
                print(f"WARNING: MATERIAL {name} IS INVALID")
                if self.verbose:
                    traceback.print_exception(type(err), err, err.__traceback__)
        if name not in self._fallback_materials:
            self._fallback_materials[name] = bpy.data.materials.new(name)
        return 1, 1, self._fallback_materials[name]

    # based on http://mattn.ufoai.org/files/MAPFiles.pdf
    def _load_solid(self, solid: vmfpy.VMFSolid, parent: str, collection: bpy.types.Collection) -> None:
        is_tool = all(side.material.lower().startswith("tools") for side in solid.sides)
        if self.skip_tools and is_tool:
            return
        name = f"{parent}_{solid.id}"
        if self.verbose:
            print(f"Building {name}...")
        side_planes: List[VectorPair] = [_plane_from_points(*side.plane) for side in solid.sides]
        if self.verbose:
            print("\nSource planes:")
            for idx, plane in enumerate(side_planes):
                print(f"    {idx}: Point on plane: {tuple(plane[0])}, Normal: Vector({tuple(plane[1])})")
        vertices: List[Vector] = []  # all vertices for this solid
        materials: List[bpy.types.Material] = []
        # vertices for each face: face_vertices[face_index] = list of indices to vertices
        face_vertices: List[List[int]] = [[] for _ in range(len(side_planes))]
        face_materials: List[int] = []
        face_loop_uvs: List[List[Tuple[float, float]]] = [[] for _ in range(len(side_planes))]
        if self.verbose:
            print("\nPlane intersection:")
        # intersect every combination of 3 planes to get possible vertices
        idx_a: int
        idx_b: int
        idx_c: int
        for idx_a, idx_b, idx_c in combinations(range(len(side_planes)), 3):
            if self.verbose:
                print(f"    Intersecting planes {idx_a}, {idx_b}, {idx_c}")
            point = _intersect_planes(side_planes[idx_a], side_planes[idx_b], side_planes[idx_c])
            if point is None:
                if self.verbose:
                    print(f"        Planes don't intersect, continuing")
                continue
            # check that the point is not outside the brush (cut off by any other plane)
            if self.verbose:
                print(f"        Intersection point: {tuple(point)}")
                print("        Checking if point is cut off by other planes")
            for idx, side_plane in enumerate(side_planes):
                if idx == idx_a or idx == idx_b or idx == idx_c:
                    continue
                dist = geometry.distance_point_to_plane(point, *side_plane)
                if dist > _CUT_EPSILON:
                    if self.verbose:
                        print(f"            Plane {idx}: Point is cut off, ignoring")
                    break
                if self.verbose:
                    print(f"             Plane {idx}: Point is not cut off")
            else:
                if self.verbose:
                    print("        Comparing point to other points on the side planes")
                # check if the point is close enough to any other vertice on the planes to be within error margin
                plane_center = (side_planes[idx_a][0] + side_planes[idx_b][0] + side_planes[idx_c][0]) / 3
                for v_idx in chain(face_vertices[idx_a], face_vertices[idx_b], face_vertices[idx_c]):
                    if _vec_isclose(vertices[v_idx], point, plane_center, self.epsilon, 0.005):
                        point_idx = v_idx
                        if self.verbose:
                            print(f"            Point is close enough to {v_idx} {tuple(vertices[v_idx])} "
                                  "to be within error margin, using existing")
                        break
                else:
                    if self.verbose:
                        print("            Point is new, saving point")
                    point_idx = len(vertices)
                    vertices.append(point)
                # the point is on every face plane intersected to create it
                if point_idx not in face_vertices[idx_a]:
                    if self.verbose:
                        print(f"        Adding point to vertices associated with plane {idx_a}")
                    face_vertices[idx_a].append(point_idx)
                if point_idx not in face_vertices[idx_b]:
                    if self.verbose:
                        print(f"        Adding point to vertices associated with plane {idx_b}")
                    face_vertices[idx_b].append(point_idx)
                if point_idx not in face_vertices[idx_c]:
                    if self.verbose:
                        print(f"        Adding point to vertices associated with plane {idx_c}")
                    face_vertices[idx_c].append(point_idx)

        if self.verbose:
            print("\nSorting face vertices:")
        # sort face vertices in clockwise order
        for face_idx, vertice_idxs in enumerate(face_vertices):
            if self.verbose:
                print(f"    Working on face created from plane {face_idx}")
                print("        Face vertices:")
                for idx in vertice_idxs:
                    print(f"            {idx}: {tuple(vertices[idx])}")
            # TODO remove invalid faces instead of erroring?
            if len(vertice_idxs) < 3:
                err = f"INVALID FACE IN {name}: NOT ENOUGH VERTS: {len(vertice_idxs)}"
                if self.verbose:
                    print(err)
                    print("INVALID MAP OR EPSILON IS TOO BIG")
                    print("ALL FACE VERTICES:")
                    for v_idx in vertice_idxs:
                        for idx in (idx for idx, polys in enumerate(face_vertices) if v_idx in polys):
                            print(f"{idx} Plane({', '.join(str(tuple(v)) for v in solid.sides[idx].plane)})")
                        print(f"INTERSECTION --> {v_idx} {tuple(vertices[v_idx])}")
                raise Exception(err)
            # quaternion to convert 3d vertices into 2d vertices on the side plane
            rot_normalize = side_planes[face_idx][1].rotation_difference(Vector((0, 0, 1)))
            # face vertices converted to 2d on the side plane
            face_vertices_2d = [(rot_normalize @ vertices[i]).to_2d() for i in vertice_idxs]
            face_center_vert = sum(face_vertices_2d, Vector((0, 0))) / len(face_vertices_2d)
            # start from the first vertice
            last_line = face_vertices_2d[0] - face_center_vert
            if self.verbose:
                print("        2D face vertices (on the plane):")
                for idx, vert in enumerate(face_vertices_2d):
                    print(f"            {vertice_idxs[idx]}: {tuple(vert)}")
                print(f"        2D face center point: {tuple(face_center_vert)}")
                print("        Sorting vertices in clockwise order based on the rotation of the direction vector")
                print(f"            Starting from first vertice: {tuple(face_vertices_2d[0])}, "
                      f"direction from center: Vector({tuple(last_line)})")
            for idx, vertice_idx in islice(enumerate(vertice_idxs), 1, None):
                # gets the rotation to the last vertice, or infinity if the rotation is negative
                def min_key(t: Tuple[int, Vector]) -> float:
                    line = t[1] - face_center_vert
                    result = last_line.angle_signed(line)
                    return inf if result < 0 else result
                # get the vertice that has the smallest positive rotation to the last one
                # skip already sorted vertices
                next_idx, next_vertice = min(enumerate(face_vertices_2d[idx:], idx), key=min_key)
                last_line = next_vertice - face_center_vert
                if self.verbose:
                    print(f"            Next vertice: {tuple(next_vertice)}, "
                          f"direction from center: Vector({tuple(last_line)})")
                # swap the list elements to sort them
                vertice_idxs[idx], vertice_idxs[next_idx] = vertice_idxs[next_idx], vertice_idxs[idx]
                face_vertices_2d[idx], face_vertices_2d[next_idx] = face_vertices_2d[next_idx], face_vertices_2d[idx]
            if self.verbose:
                print("        Sorted face vertices:")
                for idx in vertice_idxs:
                    print(f"            {idx}: {tuple(vertices[idx])}")

        # need to track side ids and corresponding verts and faces for overlays
        if self.import_overlays:
            for side_idx, side in enumerate(solid.sides):
                self._side_face_vertices[side.id] = [[i for i in range(len(face_vertices[side_idx]))]]
                self._side_vertices[side.id] = [vertices[i] for i in face_vertices[side_idx]]
                self._side_normals[side.id] = side_planes[side_idx][1]

        if self.verbose:
            print("\nCalculating UV coordinates:")
        # create uvs and materials
        for side_idx, side in enumerate(solid.sides):
            texture_width, texture_height, material = self._load_material(side.material, side.get_material)
            if material not in materials:
                material_idx = len(materials)
                materials.append(material)
            else:
                material_idx = materials.index(material)
            face_materials.append(material_idx)
            if self.verbose:
                print(f"    Working on face created from plane {side_idx}")
                print(f"        Texture dimensions: {texture_width} x {texture_height}")
                print("        Original UV coordinates:")
            for vertice_idx in face_vertices[side_idx]:
                face_loop_uvs[side_idx].append((
                    ((vertices[vertice_idx] @ Vector(side.uaxis[:3]))
                     / (texture_width * side.uaxis.scale) + side.uaxis.trans / texture_width),
                    ((vertices[vertice_idx] @ Vector(side.vaxis[:3]))
                     / (texture_height * side.vaxis.scale) + side.vaxis.trans / texture_height) * -1,
                ))
                if self.verbose:
                    print(f"            Vertice {vertice_idx} {tuple(vertices[vertice_idx])}: "
                          f"UV {face_loop_uvs[side_idx][-1]}")

            if self.verbose:
                print(f"        Normalizing UVs")
            # normalize uvs
            nearest_u = face_loop_uvs[side_idx][0][0]
            for loop_uv in face_loop_uvs[side_idx]:
                if not abs(loop_uv[0]) > 1:
                    nearest_u = 0
                    break
                if abs(loop_uv[0]) < abs(nearest_u):
                    nearest_u = loop_uv[0]
            else:
                nearest_u = floor(nearest_u) if nearest_u > 0 else ceil(nearest_u)
            nearest_v = face_loop_uvs[side_idx][0][1]
            for loop_uv in face_loop_uvs[side_idx]:
                if not abs(loop_uv[1]) > 1:
                    nearest_v = 0
                    break
                if abs(loop_uv[1]) < abs(nearest_v):
                    nearest_v = loop_uv[1]
            else:
                nearest_v = floor(nearest_v) if nearest_v > 0 else ceil(nearest_v)
            face_loop_uvs[side_idx] = [((uv[0] - nearest_u), (uv[1] - nearest_v)) for uv in face_loop_uvs[side_idx]]
            if self.verbose:
                print(f"        Closest whole U: {nearest_u}, V: {nearest_v}")
                print("        Final UV coords:")
                for idx, vertice_idx in enumerate(face_vertices[side_idx]):
                    print(f"            Vertice {vertice_idx} {tuple(vertices[vertice_idx])}: "
                          f"UV {face_loop_uvs[side_idx][idx]}")

        is_displacement = any(side.dispinfo is not None for side in solid.sides)

        if is_displacement:
            # get rid of non-displacement data
            old_vertices = vertices
            vertices = []
            old_face_vertices = face_vertices
            face_vertices = []
            old_face_materials = face_materials
            face_materials = []
            old_face_loop_uvs = face_loop_uvs
            face_loop_uvs = []
            face_loop_cols: List[List[Tuple[float, float, float, float]]] = []
            # build displacements
            for side_idx, side in enumerate(solid.sides):
                if side.dispinfo is None:
                    continue
                if self.import_overlays:
                    self._side_face_vertices[side.id] = []
                    self._side_vertices[side.id] = []
                # displacements must be quadrilateral
                if len(old_face_vertices[side_idx]) != 4:
                    err = f"INVALID DISPLACEMENT IN {name}: INVALID AMOUNT OF VERTS: {len(old_face_vertices[side_idx])}"
                    raise Exception(err)

                # figure out which corner the start position is from original face vertices by finding closest vertice
                start_pos = Vector(side.dispinfo.startposition)
                start_idx = min(range(len(old_face_vertices[side_idx])),
                                key=lambda i: (old_vertices[old_face_vertices[side_idx][i]] - start_pos).length)
                # these are based on empirical research
                top_l_idx = start_idx
                top_r_idx = (start_idx + 3) % len(old_face_vertices[side_idx])
                btm_r_idx = (start_idx + 2) % len(old_face_vertices[side_idx])
                btm_l_idx = (start_idx + 1) % len(old_face_vertices[side_idx])

                # create displacement vertices, 2d array (row, column) for every vertice, contains indices into vertices
                disp_vertices: List[List[int]] = []
                disp_loop_uvs: List[List[Tuple[float, float]]] = []
                for row_idx in range(side.dispinfo.dimension):
                    disp_vertices.append([])
                    disp_loop_uvs.append([])
                    if row_idx == 0:  # take existing vertice from the original face if this is a corner
                        row_vert_i_a = len(vertices)
                        vertices.append(old_vertices[old_face_vertices[side_idx][top_l_idx]])
                        row_vert_uv_a = old_face_loop_uvs[side_idx][top_l_idx]
                        row_vert_i_b = len(vertices)
                        vertices.append(old_vertices[old_face_vertices[side_idx][top_r_idx]])
                        row_vert_uv_b = old_face_loop_uvs[side_idx][top_r_idx]
                    elif row_idx == side.dispinfo.dimension - 1:
                        row_vert_i_a = len(vertices)
                        vertices.append(old_vertices[old_face_vertices[side_idx][btm_l_idx]])
                        row_vert_uv_a = old_face_loop_uvs[side_idx][btm_l_idx]
                        row_vert_i_b = len(vertices)
                        vertices.append(old_vertices[old_face_vertices[side_idx][btm_r_idx]])
                        row_vert_uv_b = old_face_loop_uvs[side_idx][btm_r_idx]
                    else:  # if this is not a corner, create a new vertice by interpolating between corner vertices
                        row_vert_i_a = len(vertices)
                        vertices.append(old_vertices[old_face_vertices[side_idx][top_l_idx]].lerp(
                            old_vertices[old_face_vertices[side_idx][btm_l_idx]],
                            row_idx / (side.dispinfo.dimension - 1)
                        ))
                        row_vert_uv_a = _tuple_lerp(old_face_loop_uvs[side_idx][top_l_idx],
                                                    old_face_loop_uvs[side_idx][btm_l_idx],
                                                    row_idx / (side.dispinfo.dimension - 1))
                        row_vert_i_b = len(vertices)
                        vertices.append(old_vertices[old_face_vertices[side_idx][top_r_idx]].lerp(
                            old_vertices[old_face_vertices[side_idx][btm_r_idx]],
                            row_idx / (side.dispinfo.dimension - 1)
                        ))
                        row_vert_uv_b = _tuple_lerp(old_face_loop_uvs[side_idx][top_r_idx],
                                                    old_face_loop_uvs[side_idx][btm_r_idx],
                                                    row_idx / (side.dispinfo.dimension - 1))
                    for col_idx in range(side.dispinfo.dimension):
                        if col_idx == 0:  # if this is a side vertice, it is already created in the row loop
                            col_vert_i = row_vert_i_a
                            col_vert_uv = row_vert_uv_a
                        elif col_idx == side.dispinfo.dimension - 1:
                            col_vert_i = row_vert_i_b
                            col_vert_uv = row_vert_uv_b
                        else:  # if not, create a new vertice by interpolating the corresponding side vertices
                            col_vert_i = len(vertices)
                            vertices.append(vertices[row_vert_i_a].lerp(
                                vertices[row_vert_i_b], col_idx / (side.dispinfo.dimension - 1)
                            ))
                            col_vert_uv = _tuple_lerp(row_vert_uv_a, row_vert_uv_b,
                                                      col_idx / (side.dispinfo.dimension - 1))
                        disp_vertices[row_idx].append(col_vert_i)
                        disp_loop_uvs[row_idx].append(col_vert_uv)
                disp_loop_cols = [[(0., 0., 0., a / 255) for a in row] for row in side.dispinfo.alphas]

                if self.import_overlays:
                    self._side_vertices[side.id] = [vertices[i] for row in disp_vertices for i in row]
                    side_vertice_lookup = {v_i: i for i, v_i in enumerate(i for row in disp_vertices for i in row)}

                # create displacement faces
                for row_idx in range(len(disp_vertices) - 1):
                    for col_idx in range(len(disp_vertices[row_idx]) - 1):
                        face_materials.extend((old_face_materials[side_idx],) * 2)
                        # this creates a checker pattern of quads consisting of two triangles from the verts
                        # the diagonal line of the quad is oriented / in half of the quads and \ in others
                        if row_idx % 2 == col_idx % 2:
                            disp_face_indexes = (
                                ((row_idx + 1, col_idx), (row_idx, col_idx), (row_idx + 1, col_idx + 1)),
                                ((row_idx, col_idx), (row_idx, col_idx + 1), (row_idx + 1, col_idx + 1))
                            )
                        else:
                            disp_face_indexes = (
                                ((row_idx + 1, col_idx), (row_idx, col_idx), (row_idx, col_idx + 1)),
                                ((row_idx + 1, col_idx), (row_idx, col_idx + 1), (row_idx + 1, col_idx + 1))
                            )
                        extend_face_vertices = [[disp_vertices[r][c] for r, c in idxs] for idxs in disp_face_indexes]
                        face_vertices.extend(extend_face_vertices)
                        face_loop_uvs.extend([disp_loop_uvs[r][c] for r, c in idxs] for idxs in disp_face_indexes)
                        face_loop_cols.extend([disp_loop_cols[r][c] for r, c in idxs] for idxs in disp_face_indexes)
                        if self.import_overlays:
                            self._side_face_vertices[side.id].extend(
                                [side_vertice_lookup[v_i] for v_i in f_verts] for f_verts in extend_face_vertices
                            )

                for row_idx in range(len(disp_vertices)):
                    for col_idx in range(len(disp_vertices[row_idx])):
                        vert_idx = disp_vertices[row_idx][col_idx]
                        # apply displacement offset and normals + distances + elevation
                        vertices[vert_idx] += (Vector(side.dispinfo.offsets[row_idx][col_idx])
                                               + (Vector(side.dispinfo.normals[row_idx][col_idx])
                                                  * side.dispinfo.distances[row_idx][col_idx])
                                               + side_planes[side_idx][1] * side.dispinfo.elevation)
                        if self.import_overlays:
                            self._side_vertices[side.id].append(vertices[vert_idx])

        mesh: bpy.types.Mesh = bpy.data.meshes.new(name)

        # blender can figure out the edges
        mesh.from_pydata([v * self.scale for v in vertices], (), face_vertices)
        for material in materials:
            mesh.materials.append(material)
        uv_layer: bpy.types.MeshUVLoopLayer = mesh.uv_layers.new()
        for polygon_idx, polygon in enumerate(mesh.polygons):
            polygon.material_index = face_materials[polygon_idx]
            for loop_ref_idx, loop_idx in enumerate(polygon.loop_indices):
                uv_layer.data[loop_idx].uv = face_loop_uvs[polygon_idx][loop_ref_idx]
        if is_displacement:
            vertex_colors: bpy.types.MeshLoopColorLayer = mesh.vertex_colors.new()
            for polygon_idx, polygon in enumerate(mesh.polygons):
                polygon.use_smooth = True
                for loop_ref_idx, loop_idx in enumerate(polygon.loop_indices):
                    vertex_colors.data[loop_idx].color = face_loop_cols[polygon_idx][loop_ref_idx]
        obj: bpy.types.Object = bpy.data.objects.new(name, object_data=mesh)
        collection.objects.link(obj)
        if is_tool:
            obj.display_type = 'WIRE'

    def _load_prop(self, prop: vmfpy.VMFPropEntity, collection: bpy.types.Collection) -> None:
        name = path.splitext(prop.model)[0]
        # if self._mdl_importer is not None:
        #     obj: bpy.types.Object = self._mdl_importer.load(name, name + ".mdl", collection)
        #     obj.rotation_euler = Euler((0, 0, radians(90)))
        if self._qc_importer is not None:
            obj = self._qc_importer.load(name, collection)
            obj.rotation_euler = Euler((0, 0, radians(90)))
        else:
            raise ImportError("QC importer not found")
        scale = prop.scale * self.scale
        obj.scale = (scale, scale, scale)
        obj.location = (prop.origin.x * self.scale, prop.origin.y * self.scale, prop.origin.z * self.scale)
        obj.rotation_euler.rotate(Euler((radians(prop.angles[2]), radians(prop.angles[0]), radians(prop.angles[1]))))

    def _load_overlay(self, overlay: vmfpy.VMFOverlayEntity, collection: bpy.types.Collection) -> None:
        name = f"info_overlay_{overlay.id}"

        origin = Vector(overlay.basisorigin)
        normal = Vector(overlay.basisnormal)
        u_axis = Vector(overlay.basisu)
        v_axis = Vector(overlay.basisv)

        # matrix to convert coords from uv rotation space to world space (hopefully)
        uv_rot_to_global_matrix = Matrix((
            (u_axis.x, v_axis.x, normal.x),
            (u_axis.y, v_axis.y, normal.y),
            (u_axis.z, v_axis.z, normal.z)
        ))

        global_to_uv_rot_matrix = uv_rot_to_global_matrix.inverted()

        vertices: List[Vector] = []
        face_vertices: List[List[int]] = []

        offset = 0.1
        if overlay.renderorder is not None:
            offset *= (1 + overlay.renderorder)

        # create overlay vertices from sides, add small offset to bring them in front of sides
        vert_idx_map = {}
        for side_id in overlay.sides:
            for vertice_idxs in self._side_face_vertices[side_id]:
                current_face_vertices = []
                for vertice_idx in vertice_idxs:
                    vertice = self._side_vertices[side_id][vertice_idx]
                    vertice.freeze()
                    try:  # prevent duplicate vertices
                        vert_idx = vertices.index(vertice)
                    except ValueError:
                        vert_idx = len(vertices)
                        vertices.append(vertice)
                    current_face_vertices.append(vert_idx)
                    vert_idx_map[vertice] = vert_idx
                face_vertices.append(current_face_vertices)
        for side_id in overlay.sides:
            side_normal = self._side_normals[side_id]  # TODO: should be face normal for displacements
            for vertice_idxs in self._side_face_vertices[side_id]:
                for vertice_idx in vertice_idxs:
                    vertice = self._side_vertices[side_id][vertice_idx]
                    vertices[vert_idx_map[vertice]] = (
                        side_normal * offset + vertices[vert_idx_map[vertice]]
                    )

        # uv point space versions of overlay vertices
        uv_rot_vertices = [global_to_uv_rot_matrix @ (v - origin) for v in vertices]

        uv_points = (
            Vector(overlay.uv0),
            Vector(overlay.uv1),
            Vector(overlay.uv2),
            Vector(overlay.uv3)
        )

        up_vector = Vector((0, 0, 1))
        remove_vertices = set()

        # cut faces partially outside the uv range and mark vertices outside for removal
        for side_vert_a, side_vert_b in (uv_points[:2], uv_points[1:3], uv_points[2:4], (uv_points[3], uv_points[0])):
            cut_plane_normal: Vector = up_vector.cross(side_vert_b - side_vert_a)
            # find out which vertices are outside this uv side
            outside_vertices = {
                i for i, v in enumerate(uv_rot_vertices)
                if geometry.distance_point_to_plane(v, side_vert_a, cut_plane_normal) > 0
            }
            if len(outside_vertices) == 0:
                continue
            # mark them for removal
            remove_vertices |= outside_vertices
            # cut faces inside uv border
            for face_vert_idxs in face_vertices:
                if (all(v_idx not in outside_vertices for v_idx in face_vert_idxs)
                        or all(v_idx in outside_vertices for v_idx in face_vert_idxs)):
                    # skip faces completely on either side
                    continue
                # find a vertice inside the border,
                inside_idx = next(i for i, v_idx in enumerate(face_vert_idxs) if v_idx not in outside_vertices)
                # rotate the face vert list so that it starts from a vertice inside
                while inside_idx > 0:
                    face_vert_idxs.append(face_vert_idxs.pop(0))
                    inside_idx -= 1
                # and find the first and last face vertices that are outside the uv border,
                out_idx1 = next(i for i, v_idx in enumerate(face_vert_idxs) if v_idx in outside_vertices)
                *_, out_idx2 = (i for i, v_idx in enumerate(face_vert_idxs) if v_idx in outside_vertices)
                # and create new vertice on the uv border
                # by intersecting the first edge crossing the uv border with the uv border plane,
                split_line = (
                    uv_rot_vertices[face_vert_idxs[(out_idx1 - 1) % len(face_vert_idxs)]],
                    uv_rot_vertices[face_vert_idxs[out_idx1]],
                )
                new_vertice = geometry.intersect_line_plane(*split_line, side_vert_a, cut_plane_normal)
                try:
                    # check if the vertice already exists
                    new_vert_idx1 = uv_rot_vertices.index(new_vertice)
                except ValueError:
                    new_vert_idx1 = len(uv_rot_vertices)
                    uv_rot_vertices.append(new_vertice)
                    vertices.append(origin + uv_rot_to_global_matrix @ new_vertice)
                # do the same for the last face vertice that is outside the border
                split_line = (
                    uv_rot_vertices[face_vert_idxs[(out_idx2 + 1) % len(face_vert_idxs)]],
                    uv_rot_vertices[face_vert_idxs[out_idx2]],
                )
                new_vertice = geometry.intersect_line_plane(*split_line, side_vert_a, cut_plane_normal)
                try:
                    new_vert_idx2 = uv_rot_vertices.index(new_vertice)
                except ValueError:
                    new_vert_idx2 = len(uv_rot_vertices)
                    uv_rot_vertices.append(new_vertice)
                    vertices.append(origin + (uv_rot_to_global_matrix @ new_vertice))
                # and replace the face vertices that were outside the uv border with the 2 newly created ones
                face_vert_idxs[out_idx1:out_idx2 + 1] = new_vert_idx1, new_vert_idx2

        # ensure no new vertices are outside
        for side_vert_a, side_vert_b in (uv_points[:2], uv_points[1:3], uv_points[2:4], (uv_points[3], uv_points[0])):
            cut_plane_normal = up_vector.cross(side_vert_b - side_vert_a)
            remove_vertices |= {
                i for i, v in enumerate(uv_rot_vertices)
                if geometry.distance_point_to_plane(v, side_vert_a, cut_plane_normal) > 0.001
            }

        # remove marked vertices and faces referencing them
        old_vertices = vertices
        vertices = []
        old_uv_rot_vertices = uv_rot_vertices
        uv_rot_vertices = []
        vertice_idx_map = {}
        for vertice_idx, vertice in enumerate(old_vertices):
            if vertice_idx in remove_vertices:
                continue
            vertice_idx_map[vertice_idx] = len(vertices)
            vertices.append(vertice)
            uv_rot_vertices.append(old_uv_rot_vertices[vertice_idx])

        old_face_vertices = face_vertices
        face_vertices = []
        for face_vert_idxs in old_face_vertices:
            if any(v_idx in remove_vertices for v_idx in face_vert_idxs):
                continue
            face_vertices.append([vertice_idx_map[v_idx] for v_idx in face_vert_idxs])

        # calculate projective transformation for the vertices into uvs based on the 4 supplied points
        # https://math.stackexchange.com/a/339033
        # FIXME: should be probably linear, not projective

        # compute matrix for mapping global coordinates to basis vectors
        coeff_matrix = Matrix((
            (uv_points[0].x, uv_points[1].x, uv_points[2].x),
            (uv_points[0].y, uv_points[1].y, uv_points[2].y),
            (1, 1, 1)
        ))
        coeffs: Vector = coeff_matrix.inverted() @ Vector((uv_points[3].x, uv_points[3].y, 1))
        basis_to_global = Matrix((
            (coeffs.x * uv_points[0].x, coeffs.y * uv_points[1].x, coeffs.z * uv_points[2].x),
            (coeffs.x * uv_points[0].y, coeffs.y * uv_points[1].y, coeffs.z * uv_points[2].y),
            (coeffs.x, coeffs.y, coeffs.z)
        ))
        global_to_basis = basis_to_global.inverted()

        # matrix for mapping basis vectors to uv coordinates
        u1, u2, v1, v2 = overlay.startu, overlay.endu, overlay.startv, overlay.endv
        coeff_matrix = Matrix((
            (u1, u1, u2),
            (v2, v1, v1),
            (1, 1, 1)
        ))
        coeffs = coeff_matrix.inverted() @ Vector((u2, v2, 1))
        basis_to_uv = Matrix((
            (coeffs.x * u1, coeffs.y * u1, coeffs.z * u2),
            (coeffs.x * v2, coeffs.y * v1, coeffs.z * v1),
            (coeffs.x, coeffs.y, coeffs.z)
        ))

        # combined matrix to map global to uv
        map_matrix = basis_to_uv @ global_to_basis

        # calculate texture coordinates for the vertices
        face_loop_uvs: List[List[Tuple[float, float]]] = []
        for face_vert_idxs in face_vertices:
            face_uvs: List[Tuple[float, float]] = []
            for vert_idx in face_vert_idxs:
                uv_vertice = uv_rot_vertices[vert_idx]
                uv_vertice.z = 1
                product_vec = map_matrix @ uv_vertice
                face_uvs.append((product_vec.x / product_vec.z, product_vec.y / product_vec.z))
            face_loop_uvs.append(face_uvs)

        mesh: bpy.types.Mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([v * self.scale for v in vertices], (), face_vertices)
        _, _, material = self._load_material(overlay.material, overlay.get_material)
        mesh.materials.append(material)
        uv_layer: bpy.types.MeshUVLoopLayer = mesh.uv_layers.new()
        for polygon_idx, polygon in enumerate(mesh.polygons):
            for loop_ref_idx, loop_idx in enumerate(polygon.loop_indices):
                uv_layer.data[loop_idx].uv = face_loop_uvs[polygon_idx][loop_ref_idx]
        obj: bpy.types.Object = bpy.data.objects.new(name, object_data=mesh)
        collection.objects.link(obj)
