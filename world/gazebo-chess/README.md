# gazebo-chess 世界（ANIMA Zero v0.4，最小版）

sim-chess 那张棋桌的 **Gazebo 3D 物理版**：真实建模的 episode 六轴机械臂，用**真实夹爪**把棋子从一格夹起、挪到另一格。对大脑（ANIMA）只露和 sim-chess 一模一样的 AWI（能力/感知/动作），世界内部把 ROS2 + MoveIt + Gazebo 这一摊全包起来。

> v0.4 故意砍到最小：盘上**一个子**，机械臂能真夹起来挪一下，跑通整条 infra。多子、失败补救、位置评估见 v0.5（计划在 `~/.claude/plans/1-gazebo-chess-0-5-multi-piece-failure-recovery.md`）。

## 它和大脑怎么对话（AWI，和 sim-chess 同一套）

- `GET /capabilities` —— 报工具：take_seat / seat_opponent / start_game / move / resign。
- `GET /perceive` —— 给画面（俯视相机帧）+ 极简 state `{controllers, phase}`，**绝不给棋盘真值**。
- `POST /invoke` —— 收动作；`move` 内部 = 真跑一趟夹取+搬运+放下 + 自检。
- `GET /health` / `GET /stream`（人看的视频）/ `GET /`（人类页）。

## 它内部怎么跟仿真说话（ROS2 + MoveIt）

- 机械臂运动：MoveIt `/move_action`（避障规划）；逆解/可达 `/compute_ik`、`/check_state_validity`。
- 夹爪：`gripper_controller`（真实闭合夹住子）。
- 往 Gazebo 塞棋盘/棋子/相机：`ros_gz_sim create`；读真值：pose 话题 / `set_entity_pose`。
- 相机：Gazebo 俯视相机 → `ros_gz_image image_bridge` → 订阅 → 转 JPEG → /perceive + /stream。

## 怎么起（前提：episode 仿真栈由用户亲手起）

```bash
# 终端1（用户亲手起 ROS 仿真栈）
ros2 launch episode1_gz_sim sim.launch.py headless:=true rviz:=false
# 终端2（gazebo-chess 世界服务，:8106）
cd .../anima-zero/world/gazebo-chess && source .venv/bin/activate && uvicorn server:app --port 8106 --reload
```

> venv 用 `python3 -m venv --system-site-packages .venv` 建，好 import 系统 ROS2。

## 全部可调项

见 `config.py`（`GZCHESS_*` 环境变量，默认值集中在那里，禁硬编码）。

## 当前进度（v0.4 封版）

- [x] `config.py`、`geometry.py`（坐标换算，已离线自测通过）
- [x] 棋子/棋盘/相机模型 + 往 Gazebo spawn（`spawn.py` / `models.py`）
- [x] 俯视相机出图（Gazebo 相机 → `ros_gz_image image_bridge` → `vision.py` → JPEG）
- [x] `arm_controller.py`（MoveIt `/compute_ik` + FK 复核 + `FollowJointTrajectory`）、`grasp_pose.py`
- [x] `server.py` / `world.py` 接 MCP（`awi_mcp.py`，接口和 sim-chess 同款）
- [x] **teleop 手动遥控（`:8110`）**：人可顺畅点动这条臂，物理底座已验通（见 `episode-ros-ws` 的 `episode_teleop` + 项目 `运行命令.md`「三 · teleop」）
- [x] **ANIMA 自主走子（大脑发 `move` → 世界内部真跑一趟夹取搬运）——v0.5 wave 0 已修通**。
      v0.4 的 `TimeoutError` 根因是框架级的：世界把几十秒的夹取同步跑在事件循环上（move 期间整个
      服务器冻结、进度发不出去），大脑又用固定死线盲等。修法＝采标 MCP progress：世界把活儿放到
      工作线程、分阶段报人话进度（「已夹取，正在移向 e4」），大脑「有进度就续命、失联才判死」。
      实测：move ~26s 完成，期间 `/health` 全程 <2ms 响应，进度实时上 AWI 仪表盘与对弈面板。
- [ ] 多子、失败补救、位置评估 —— v0.5 后续 wave（见 `~/.claude/plans/0-5-0-5-anima-zero-v0-5-woolly-rabin.md`）

> v0.4 交付的是「物理世界基础设施 + 手动遥控」；v0.5 wave 0 把「自主走子」这条链路修通，
> **完整对弈（视觉读盘 + 多子 + 失败补救）是 v0.5 后续 wave 的目标**。
