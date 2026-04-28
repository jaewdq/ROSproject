from pxr import UsdGeom, Gf
import omni.usd

# =========================
# 기본 설정
# =========================
STAGE_ROOT = "/World/WarehouseDemo"

FLOOR_SIZE_X = 6.0
FLOOR_SIZE_Y = 6.0
FLOOR_THICKNESS = 0.02

SHELF_WIDTH = 1.20
SHELF_DEPTH = 0.40
SHELF_HEIGHT = 1.25

POST_THICKNESS = 0.03
BOARD_THICKNESS = 0.035

BOARD_LEVELS = [0.18, 0.62, 1.06]

# -------------------------
# 사용자 스케치 기준 배치
# -------------------------
SHELF_POSITIONS = {
    "A_01": (-1.9,  1.6),
    "A_02": (-1.9, -1.2),
    "B_01": ( 0.2,  1.6),
    "B_02": ( 0.2, -1.2),
}

STAGING_CENTER = (2.1, 1.9)
STAGING_SIZE = (0.90, 0.90, 0.02)

HOME_CENTER = (2.1, -1.9)
HOME_RADIUS_MARK = 0.35

COLOR_FLOOR = [(0.82, 0.82, 0.82)]
COLOR_POST = [(0.07, 0.07, 0.07)]
COLOR_BOARD = [(0.45, 0.31, 0.20)]
COLOR_LABEL = [(0.10, 0.35, 0.90)]
COLOR_TEXT = [(1.00, 1.00, 1.00)]
COLOR_MARK = [(0.95, 0.80, 0.10)]
COLOR_STAGE = [(0.60, 0.60, 0.60)]
COLOR_HOME = [(0.15, 0.75, 0.25)]


ctx = omni.usd.get_context()
stage = ctx.get_stage()

def remove_if_exists(path: str):
    prim = stage.GetPrimAtPath(path)
    if prim.IsValid():
        stage.RemovePrim(path)

def define_xform(path: str):
    return UsdGeom.Xform.Define(stage, path)

def set_transform(prim, translate=(0, 0, 0), scale=(1, 1, 1)):
    xform_api = UsdGeom.XformCommonAPI(prim)
    xform_api.SetTranslate(Gf.Vec3d(*translate))
    xform_api.SetScale(Gf.Vec3f(*scale))

def create_cube(path: str, translate=(0,0,0), scale=(1,1,1), color=[(1,1,1)]):
    cube = UsdGeom.Cube.Define(stage, path)
    cube.CreateSizeAttr(1.0)
    set_transform(cube, translate=translate, scale=scale)
    cube.CreateDisplayColorAttr(color)
    return cube

def create_floor():
    create_cube(
        f"{STAGE_ROOT}/Floor",
        translate=(0.0, 0.0, FLOOR_THICKNESS * 0.5),
        scale=(FLOOR_SIZE_X, FLOOR_SIZE_Y, FLOOR_THICKNESS),
        color=COLOR_FLOOR
    )

def create_home_marker():
    x, y = HOME_CENTER

    create_cube(
        f"{STAGE_ROOT}/HomeMarker",
        translate=(x, y, 0.03),
        scale=(HOME_RADIUS_MARK, HOME_RADIUS_MARK, 0.03),
        color=COLOR_HOME
    )

def create_staging_area():
    x, y = STAGING_CENTER
    sx, sy, sz = STAGING_SIZE

    create_cube(
        f"{STAGE_ROOT}/StagingArea",
        translate=(x, y, sz * 0.5 + 0.01),
        scale=(sx, sy, sz),
        color=COLOR_STAGE
    )

    # 점선 느낌으로 모서리 마커 추가
    offsets = [
        (-sx/2, -sy/2), (sx/2, -sy/2),
        (-sx/2, sy/2),  (sx/2, sy/2)
    ]
    for i, (dx, dy) in enumerate(offsets):
        create_cube(
            f"{STAGE_ROOT}/StagingCorner_{i+1}",
            translate=(x + dx, y + dy, 0.08),
            scale=(0.06, 0.06, 0.08),
            color=COLOR_TEXT
        )

def create_shelf(name: str, center_x: float, center_y: float):
    shelf_root = f"{STAGE_ROOT}/{name}"
    define_xform(shelf_root)

    half_w = SHELF_WIDTH * 0.5
    half_d = SHELF_DEPTH * 0.5
    half_h = SHELF_HEIGHT * 0.5

    post_positions = [
        (center_x - half_w + POST_THICKNESS * 0.5, center_y - half_d + POST_THICKNESS * 0.5, half_h),
        (center_x + half_w - POST_THICKNESS * 0.5, center_y - half_d + POST_THICKNESS * 0.5, half_h),
        (center_x - half_w + POST_THICKNESS * 0.5, center_y + half_d - POST_THICKNESS * 0.5, half_h),
        (center_x + half_w - POST_THICKNESS * 0.5, center_y + half_d - POST_THICKNESS * 0.5, half_h),
    ]

    for i, pos in enumerate(post_positions):
        create_cube(
            f"{shelf_root}/Post_{i+1}",
            translate=pos,
            scale=(POST_THICKNESS, POST_THICKNESS, SHELF_HEIGHT),
            color=COLOR_POST
        )

    for i, z in enumerate(BOARD_LEVELS):
        create_cube(
            f"{shelf_root}/Board_{i+1}",
            translate=(center_x, center_y, z),
            scale=(SHELF_WIDTH, SHELF_DEPTH, BOARD_THICKNESS),
            color=COLOR_BOARD
        )

    # 라벨판
    label_plate_w = 0.44
    label_plate_d = 0.02
    label_plate_h = 0.18
    label_plate_z = SHELF_HEIGHT + 0.10

    create_cube(
        f"{shelf_root}/LabelPlate",
        translate=(center_x, center_y + half_d + 0.04, label_plate_z),
        scale=(label_plate_w, label_plate_d, label_plate_h),
        color=COLOR_LABEL
    )

    # 간단한 시각 패턴 (A/B 구분)
    if name.startswith("A"):
        left_marks = [
            (-0.12, 0.03), (-0.16, -0.03), (-0.08, -0.03)
        ]
    else:
        left_marks = [
            (-0.12, 0.05), (-0.12, 0.00), (-0.12, -0.05)
        ]

    for i, (dx, dz) in enumerate(left_marks):
        create_cube(
            f"{shelf_root}/LabelLetterMark_{i+1}",
            translate=(center_x + dx, center_y + half_d + 0.055, label_plate_z + dz),
            scale=(0.035, 0.012, 0.035),
            color=COLOR_TEXT
        )

    # 숫자 구분 (01 / 02)
    if name.endswith("01"):
        num_marks = [
            (0.09, 0.05), (0.09, 0.00), (0.09, -0.05)
        ]
    else:
        num_marks = [
            (0.07, 0.05), (0.11, 0.05), (0.11, 0.00), (0.07, -0.05), (0.11, -0.05)
        ]

    for i, (dx, dz) in enumerate(num_marks):
        create_cube(
            f"{shelf_root}/LabelNumberMark_{i+1}",
            translate=(center_x + dx, center_y + half_d + 0.055, label_plate_z + dz),
            scale=(0.03, 0.012, 0.03),
            color=COLOR_MARK
        )

    # 드론이 접근할 전면 목표 마커
    create_cube(
        f"{shelf_root}/TargetMarker",
        translate=(center_x, center_y - 0.55, 0.03),
        scale=(0.28, 0.28, 0.03),
        color=COLOR_MARK
    )

def create_origin_marker():
    create_cube(
        f"{STAGE_ROOT}/OriginMarker",
        translate=(0.0, 0.0, 0.03),
        scale=(0.18, 0.18, 0.03),
        color=[(1.0, 0.0, 0.0)]
    )

def build_scene():
    remove_if_exists(STAGE_ROOT)
    define_xform(STAGE_ROOT)

    create_floor()
    create_origin_marker()
    create_staging_area()
    create_home_marker()

    for shelf_name, (x, y) in SHELF_POSITIONS.items():
        create_shelf(shelf_name, x, y)

    print("Warehouse layout created.")
    print("Home center:", HOME_CENTER)
    print("Staging area:", STAGING_CENTER)
    print("Shelves:", SHELF_POSITIONS)

build_scene()
