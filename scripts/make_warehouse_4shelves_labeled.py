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

# 선반판 높이(중심 기준)
BOARD_LEVELS = [0.18, 0.62, 1.06]

# 선반 위치 (center x, y)
SHELF_POSITIONS = {
    "A_1": (-1.2,  1.2),
    "A_2": ( 1.2,  1.2),
    "B_1": (-1.2, -1.2),
    "B_2": ( 1.2, -1.2),
}

# 색상
COLOR_FLOOR = [(0.82, 0.82, 0.82)]
COLOR_POST  = [(0.07, 0.07, 0.07)]   # 검은 프레임
COLOR_BOARD = [(0.45, 0.31, 0.20)]   # 갈색 선반판
COLOR_LABEL = [(0.10, 0.35, 0.90)]   # 라벨판 파랑
COLOR_TEXT  = [(1.00, 1.00, 1.00)]   # 흰색 글자 느낌용
COLOR_MARK  = [(0.95, 0.80, 0.10)]   # 노란 강조

# =========================
# 유틸
# =========================
ctx = omni.usd.get_context()
stage = ctx.get_stage()

def remove_if_exists(path: str):
    prim = stage.GetPrimAtPath(path)
    if prim.IsValid():
        stage.RemovePrim(path)

def define_xform(path: str):
    return UsdGeom.Xform.Define(stage, path)

def set_transform(prim, translate=(0,0,0), scale=(1,1,1)):
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

def create_shelf(name: str, center_x: float, center_y: float):
    shelf_root = f"{STAGE_ROOT}/{name}"
    define_xform(shelf_root)

    half_w = SHELF_WIDTH * 0.5
    half_d = SHELF_DEPTH * 0.5
    half_h = SHELF_HEIGHT * 0.5

    # 4개 기둥
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

    # 선반판 3단
    for i, z in enumerate(BOARD_LEVELS):
        create_cube(
            f"{shelf_root}/Board_{i+1}",
            translate=(center_x, center_y, z),
            scale=(SHELF_WIDTH, SHELF_DEPTH, BOARD_THICKNESS),
            color=COLOR_BOARD
        )

    # 라벨판 배경
    label_plate_w = 0.42
    label_plate_d = 0.02
    label_plate_h = 0.18
    label_plate_z = SHELF_HEIGHT + 0.10

    create_cube(
        f"{shelf_root}/LabelPlate",
        translate=(center_x, center_y + half_d + 0.04, label_plate_z),
        scale=(label_plate_w, label_plate_d, label_plate_h),
        color=COLOR_LABEL
    )

    # 문자 대신 블록 패턴으로 간단하게 시각 구분
    # 첫 글자(A/B) 표시용 왼쪽 마커
    if name.startswith("A"):
        # A 계열: 위 삼각형 느낌 블록 3개
        mark_positions = [
            (center_x - 0.10, center_y + half_d + 0.055, label_plate_z + 0.03),
            (center_x - 0.14, center_y + half_d + 0.055, label_plate_z - 0.03),
            (center_x - 0.06, center_y + half_d + 0.055, label_plate_z - 0.03),
        ]
    else:
        # B 계열: 세로 막대 느낌 블록 3개
        mark_positions = [
            (center_x - 0.11, center_y + half_d + 0.055, label_plate_z + 0.05),
            (center_x - 0.11, center_y + half_d + 0.055, label_plate_z),
            (center_x - 0.11, center_y + half_d + 0.055, label_plate_z - 0.05),
        ]

    for j, p in enumerate(mark_positions):
        create_cube(
            f"{shelf_root}/LetterMark_{j+1}",
            translate=p,
            scale=(0.035, 0.012, 0.035),
            color=COLOR_TEXT
        )

    # 숫자(1/2) 표시용 오른쪽 마커
    if name.endswith("1"):
        number_positions = [
            (center_x + 0.10, center_y + half_d + 0.055, label_plate_z + 0.04),
            (center_x + 0.10, center_y + half_d + 0.055, label_plate_z),
            (center_x + 0.10, center_y + half_d + 0.055, label_plate_z - 0.04),
        ]
    else:
        number_positions = [
            (center_x + 0.08, center_y + half_d + 0.055, label_plate_z + 0.04),
            (center_x + 0.12, center_y + half_d + 0.055, label_plate_z + 0.04),
            (center_x + 0.12, center_y + half_d + 0.055, label_plate_z),
            (center_x + 0.08, center_y + half_d + 0.055, label_plate_z - 0.04),
            (center_x + 0.12, center_y + half_d + 0.055, label_plate_z - 0.04),
        ]

    for j, p in enumerate(number_positions):
        create_cube(
            f"{shelf_root}/NumberMark_{j+1}",
            translate=p,
            scale=(0.03, 0.012, 0.03),
            color=COLOR_MARK
        )

    # 선반 앞 목표 지점 마커 (드론이 가야 할 위치 시각화용)
    create_cube(
        f"{shelf_root}/TargetMarker",
        translate=(center_x, center_y - 0.55, 0.03),
        scale=(0.28, 0.28, 0.03),
        color=COLOR_MARK
    )

def create_reference_axes():
    # 중앙 기준 위치 확인용 작은 축 마커
    create_cube(
        f"{STAGE_ROOT}/OriginMarker",
        translate=(0.0, 0.0, 0.03),
        scale=(0.20, 0.20, 0.03),
        color=[(1.0, 0.0, 0.0)]
    )

def build_scene():
    remove_if_exists(STAGE_ROOT)
    define_xform(STAGE_ROOT)

    create_floor()
    create_reference_axes()

    for shelf_name, (x, y) in SHELF_POSITIONS.items():
        create_shelf(shelf_name, x, y)

    print("Warehouse scene created successfully.")
    print("Root:", STAGE_ROOT)
    print("Shelves:", list(SHELF_POSITIONS.keys()))
    print("Target markers are placed in front of each shelf.")

build_scene()
