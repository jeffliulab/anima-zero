# gazebo-chess 世界（ANIMA Zero v0.5）

sim-chess 那张棋桌的 **Gazebo 3D 物理版**：真实建模的 episode 六轴机械臂，用**真实夹爪**把棋子从一格夹起、挪到另一格。对大脑（ANIMA）只露标准 MCP 接口（和 sim-chess 同款），世界内部把 ROS2 + MoveIt + Gazebo 这一摊全包起来。

> v0.4 跑通最小 infra（单子 + 手动遥控）；**v0.5 长成完整形态**：斜视相机（看得出子型）、
> `GZCHESS_SETUP_FEN` 多子摆盘（棋子分六型剪影，碰撞体不变）、长动作 MCP progress（move 期间
> 服务器不冻结、进度实时可见）、失败注入/执行自检/补救。大脑侧的双层视觉桥见脑仓 `src/tools/boardgame/`。

## 它和大脑怎么对话（标准 MCP，挂在 `/mcp`）

- `tools/list` + `tools/call` —— 三个物理原语：`move`(裸搬)/`remove`(夹去弃子区)/`place`(备用区取子摆盘)；
  长动作边执行边发 `notifications/progress`（人话阶段：定位→抓→搬→放→核对）。
- `resources/read anima://observation` —— 给画面（相机帧）+ 空 state，**绝不给棋盘真值**。
- `prompts/get "guidance"` —— 世界说明书（注入大脑系统提示）。
- 带外普通 HTTP：`/health`（探活）/ `/status`（人类调试台真值，不给大脑）/ `/stream`（人看的视频）/ `/`（人类页）。

## 它内部怎么跟仿真说话（ROS2 + MoveIt）

- 机械臂运动：MoveIt `/compute_ik`（+ FK 复核防 IKFast 假解）→ `FollowJointTrajectory` 执行；
  抓取候选按「指尖离邻子净空」排序（多子防撞）。
- 夹爪：`gripper_controller`（真实闭合夹住子；张开度收窄到指尖不出本格）。
- ROS spin 收敛到**唯一专职线程**（请求线程只对 future 挂事件等待，绝不自己 spin——从请求线程
  spin 会和 DDS 撞线程卡死，v0.5 实测教训）。
- 往 Gazebo 塞棋盘/棋子/相机：`ros_gz_sim create`；读真值：pose 话题（只用于 /status 与执行自检）。
- 相机：Gazebo 相机（默认斜视，`GZCHESS_CAM_MODE=overhead` 切回俯视）→ `ros_gz_image image_bridge` → 订阅 → /perceive + /stream。
- 离线工具：`scripts/gen_dataset.py`（合成训练数据，世界真值自动打标签）+ `scripts/train_cnn.py`
  （离线 torch 训练导出 ONNX，不进任何运行时）。

## 怎么起（前提：episode 仿真栈由用户亲手起）

```bash
# 终端1（用户亲手起 ROS 仿真栈）
ros2 launch episode1_gz_sim sim.launch.py headless:=true rviz:=false
# 终端1b（相机图桥，见项目 运行命令.md 二·4）
ros2 run ros_gz_image image_bridge /gazebo_chess/overhead/image
# 终端2（gazebo-chess 世界服务，:8106；可选 GZCHESS_SETUP_FEN 摆多子）
cd .../anima-zero/world/gazebo-chess && source .venv/bin/activate && \
GZCHESS_SETUP_FEN="4k3/8/8/8/8/8/4P3/4K3" uvicorn server:app --port 8106 --reload
```

> venv 用 `python3 -m venv --system-site-packages .venv` 建，好 import 系统 ROS2。

## 全部可调项

见 `config.py`（`GZCHESS_*` 环境变量，默认值集中在那里，禁硬编码）。

## 当前进度（v0.5）

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
- [x] **多子摆盘**（`GZCHESS_SETUP_FEN`）+ 棋子六型剪影（视觉分型，碰撞体全型一致=抓取物理不变）
- [x] **斜视相机**（默认；俯视保留可切）+ 合成数据管线（`scripts/gen_dataset.py` / `train_cnn.py`）
- [x] **失败注入 + 执行自检分类 + 大脑补救**（夹空原样重试 / 放偏从实际落格夹回）——活体验收通过
- [x] **活体对弈验收**：王兵残局 4 个半回合——大脑经斜视相机读盘、纯视觉认出对手挪子、真夹真放，
      信念盘与世界真值一致
- [ ] 吃子/升变/易位的视觉识别、扶正倒子、弃子区实测校准、真机（C920 域适配）——后续版本
