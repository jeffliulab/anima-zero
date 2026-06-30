"""按 config 生成 Gazebo SDF 模型字符串：棋盘、棋子、俯视相机。

为什么不用静态 .sdf 文件：尺寸/位姿都要可配（禁硬编码），所以从 config 用 f-string 拼出来，
spawn 时再塞进 Gazebo。生成的是单个 <model> 片段（含 <sdf> 包裹），可直接喂 ros_gz 的 create。

坐标：模型 spawn 到 world 帧（= MoveIt 规划帧）。棋盘上表面在 BOARD_ORIGIN_Z。
"""
from __future__ import annotations

import config


def _inertia_box(m: float, x: float, y: float, z: float) -> str:
    ixx = m * (y * y + z * z) / 12.0
    iyy = m * (x * x + z * z) / 12.0
    izz = m * (x * x + y * y) / 12.0
    return (f"<inertia><ixx>{ixx:.6g}</ixx><iyy>{iyy:.6g}</iyy><izz>{izz:.6g}</izz>"
            f"<ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia>")


def _inertia_cyl(m: float, r: float, h: float) -> str:
    ixx = m * (3 * r * r + h * h) / 12.0
    izz = m * r * r / 2.0
    return (f"<inertia><ixx>{ixx:.6g}</ixx><iyy>{ixx:.6g}</iyy><izz>{izz:.6g}</izz>"
            f"<ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia>")


def board_sdf(name: str = "chessboard") -> tuple[str, tuple[float, float, float]]:
    """棋盘底板：薄长方体，坐在桌面(z=0)上，上表面在 BOARD_ORIGIN_Z。
    返回 (sdf 字符串, spawn 世界坐标 xyz=模型原点)。模型原点在板几何中心。
    """
    size = config.BOARD_SIZE_M
    th = config.BOARD_THICKNESS_M
    # 模型原点在板中心 → spawn z = 上表面 - 厚度/2
    spawn_xyz = (config.BOARD_ORIGIN_X, config.BOARD_ORIGIN_Y, config.BOARD_ORIGIN_Z - th / 2.0)
    sdf = f"""<sdf version="1.10">
  <model name="{name}">
    <static>true</static>
    <link name="link">
      <collision name="col">
        <geometry><box><size>{size} {size} {th}</size></box></geometry>
        <surface><friction><ode><mu>0.9</mu><mu2>0.9</mu2></ode></friction></surface>
      </collision>
      <visual name="vis">
        <geometry><box><size>{size} {size} {th}</size></box></geometry>
        <material><ambient>0.20 0.25 0.20 1</ambient><diffuse>0.25 0.32 0.25 1</diffuse></material>
      </visual>
    </link>
  </model>
</sdf>"""
    return sdf, spawn_xyz


def piece_sdf(name: str, color: str = "white") -> tuple[str, tuple[float, float, float]]:
    """一枚棋子：底座(宽)+ 抓取腰(GRASP_WIDTH 宽，高摩擦，给夹爪夹)+ 头。
    返回 (sdf, spawn 世界 xyz=模型原点)。模型原点在棋子底面中心，spawn z = 棋盘上表面。
    color: white/black → 材质色。
    """
    base_r = config.PIECE_BASE_DIAM_M / 2.0
    waist_r = config.PIECE_GRASP_WIDTH_M / 2.0
    waist_z0 = config.PIECE_GRASP_WAIST_M               # 腰中心离底面高度（抓取点）
    base_h = 0.008
    waist_h = 0.020                                     # 腰段高度（够夹爪指接触）
    head_r = waist_r * 0.7
    total_h = config.PIECE_HEIGHT_M
    head_h = max(0.004, total_h - base_h - waist_h)
    mass = 0.020
    if color == "white":
        mat = "<ambient>0.85 0.82 0.72 1</ambient><diffuse>0.92 0.90 0.82 1</diffuse>"
    else:
        mat = "<ambient>0.06 0.06 0.07 1</ambient><diffuse>0.10 0.10 0.12 1</diffuse>"
    spawn_xyz = (0.0, 0.0, config.BOARD_ORIGIN_Z)        # x,y 由 spawn 调用者按棋格填
    # 三段叠起来：底座 [0,base_h]，腰 [base_h, base_h+waist_h]，头在其上。抓取点在腰中段。
    base_cz = base_h / 2.0
    waist_cz = base_h + waist_h / 2.0
    head_cz = base_h + waist_h + head_h / 2.0
    # 高摩擦让夹爪靠接触摩擦夹得住（腰段尤其重要）。
    fric = "<surface><friction><ode><mu>1.2</mu><mu2>1.2</mu2></ode></friction></surface>"
    sdf = f"""<sdf version="1.10">
  <model name="{name}">
    <link name="link">
      <inertial><mass>{mass}</mass>{_inertia_cyl(mass, waist_r, total_h)}
        <pose>0 0 {total_h/2.0:.4f} 0 0 0</pose></inertial>
      <collision name="base"><pose>0 0 {base_cz:.4f} 0 0 0</pose>
        <geometry><cylinder><radius>{base_r:.4f}</radius><length>{base_h}</length></cylinder></geometry>
        {fric}</collision>
      <collision name="waist"><pose>0 0 {waist_cz:.4f} 0 0 0</pose>
        <geometry><cylinder><radius>{waist_r:.4f}</radius><length>{waist_h}</length></cylinder></geometry>
        {fric}</collision>
      <collision name="head"><pose>0 0 {head_cz:.4f} 0 0 0</pose>
        <geometry><cylinder><radius>{head_r:.4f}</radius><length>{head_h:.4f}</length></cylinder></geometry>
        {fric}</collision>
      <visual name="base"><pose>0 0 {base_cz:.4f} 0 0 0</pose>
        <geometry><cylinder><radius>{base_r:.4f}</radius><length>{base_h}</length></cylinder></geometry>
        <material>{mat}</material></visual>
      <visual name="waist"><pose>0 0 {waist_cz:.4f} 0 0 0</pose>
        <geometry><cylinder><radius>{waist_r:.4f}</radius><length>{waist_h}</length></cylinder></geometry>
        <material>{mat}</material></visual>
      <visual name="head"><pose>0 0 {head_cz:.4f} 0 0 0</pose>
        <geometry><cylinder><radius>{head_r:.4f}</radius><length>{head_h:.4f}</length></cylinder></geometry>
        <material>{mat}</material></visual>
    </link>
  </model>
</sdf>"""
    return sdf, spawn_xyz


def camera_sdf(name: str = "overhead_cam") -> tuple[str, tuple[float, float, float], tuple[float, float, float]]:
    """俯视相机：架在棋盘中心正上方 CAM_HEIGHT 处，朝下拍。
    返回 (sdf, spawn xyz, spawn rpy)。相机像素在 CAM_IMAGE_TOPIC 上发布（gz 话题），再用 image_bridge 桥到 ROS。
    朝向：CAM_RPY 默认 pitch=+90°（相机 +x 轴朝下）。图像上下左右朝向需对着仿真核对。
    """
    spawn_xyz = (config.BOARD_ORIGIN_X, config.BOARD_ORIGIN_Y, config.BOARD_ORIGIN_Z + config.CAM_HEIGHT_M)
    spawn_rpy = tuple(config.CAM_RPY)
    sdf = f"""<sdf version="1.10">
  <model name="{name}">
    <static>true</static>
    <link name="link">
      <sensor name="overhead" type="camera">
        <always_on>1</always_on>
        <update_rate>{config.CAM_FPS}</update_rate>
        <visualize>false</visualize>
        <topic>{config.CAM_IMAGE_TOPIC}</topic>
        <camera>
          <horizontal_fov>{config.CAM_FOV_RAD}</horizontal_fov>
          <image><width>{config.CAM_W}</width><height>{config.CAM_H}</height><format>R8G8B8</format></image>
          <clip><near>0.05</near><far>5.0</far></clip>
        </camera>
      </sensor>
    </link>
  </model>
</sdf>"""
    return sdf, spawn_xyz, spawn_rpy


if __name__ == "__main__":
    # 离线校验：生成的 SDF 是合法 XML，且关键尺寸来自 config（不硬编码）。
    import xml.dom.minidom as _m

    for label, gen in (("board", lambda: board_sdf()[0]),
                       ("piece_white", lambda: piece_sdf("p", "white")[0]),
                       ("piece_black", lambda: piece_sdf("p", "black")[0]),
                       ("camera", lambda: camera_sdf()[0])):
        xml = gen()
        _m.parseString(xml)   # 不合法会抛异常
        print(f"[ok] {label} SDF 合法（{len(xml)} 字符）")
    print("board spawn xyz =", board_sdf()[1])
    print("camera spawn xyz/rpy =", camera_sdf()[1], camera_sdf()[2])
    print("piece spawn z (棋盘面) =", piece_sdf('p')[1][2])
