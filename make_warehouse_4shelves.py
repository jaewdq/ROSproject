from pxr import UsdGeom, Gf, Sdf
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
COLOR_LABEL = [(0.12, 0.35, 0.85)]   # 라벨판(파랑)


# =========================
# 유틸 함수
# =========================
ctx = omni.usd.get_context()
stage = ctx.get_stage()

def remove_if_exists(path: str):
    prim = stage.GetPrimAtPath(path)
    if prim.IsValid():
        stage.RemovePrim(path)

def define_xform(path: str):
    xform = UsdGeom.Xform.Define(stage, path)
    return xform

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

    # 전면 라벨판(텍스트 대신 시각적 구분용)
    label_w = 0.22
    label_d = 0.01
    label_h = 0.10
    create_cube(
        f"{shelf_root}/LabelPlate",
        translate=(center_x, center_y + half_d + 0.015, SHELF_HEIGHT + 0.08),
        scale=(label_w, label_d, label_h),
        color=COLOR_LABEL
    )


# =========================
# 생성 실행
# =========================
remove_if_exists(STAGE_ROOT)
define_xform(STAGE_ROOT)

create_floor()

for shelf_name, (x, y) in SHELF_POSITIONS.items():
    create_shelf(shelf_name, x, y)

print("Warehouse demo created at:", STAGE_ROOT)
print("Shelves:", list(SHELF_POSITIONS.keys()))
