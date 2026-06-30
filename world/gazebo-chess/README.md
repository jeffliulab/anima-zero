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

## 当前进度（v0.4）

- [x] `config.py`、`geometry.py`（坐标换算，已离线自测通过）
- [ ] 棋子/棋盘/相机模型 + 往 Gazebo spawn
- [ ] W0 探路：相机出图、真实夹爪夹起一个子（调接触参数）
- [ ] `arm_controller.py` / `grasp_pose.py` 单子抓放
- [ ] `server.py` / `world.py` 接 AWI、接大脑跑通
