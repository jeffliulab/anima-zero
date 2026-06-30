"""机械臂抓放控制器（rclpy）：给 MoveIt 算 IK、用关节轨迹控制器执行、开合夹爪。

v0.4 走法（务实、可靠）：用 MoveIt `/compute_ik` 把"末端到某位姿"解成关节角，再用
`episode_arm_controller` 的 FollowJointTrajectory 执行；夹爪用 `gripper_controller` 同理。
（full move_action 规划+避障更稳，但目标构造复杂；0.4 一个子、开阔棋盘，IK+轨迹够用，且我已验证轨迹可执行。
 桌面/棋子避障靠把接近点抬高 + 抓取点在板面上方，不往桌里扎。更强避障留 0.5 换 move_action。）

抓取 = 真实夹爪物理夹取（闭合到夹持宽度，靠接触摩擦夹住子），不贴关节。
"""
from __future__ import annotations

import time

import rclpy
from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory
from moveit_msgs.msg import RobotState
from moveit_msgs.srv import GetPositionFK, GetPositionIK
from rclpy.action import ActionClient
from rclpy.node import Node
from sensor_msgs.msg import JointState
from geometry_msgs.msg import PoseStamped
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

import config
import grasp_pose

ARM_JOINTS = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
GRIPPER_JOINTS = ["left_finger_joint", "right_finger_joint"]


class ArmController(Node):
    def __init__(self) -> None:
        super().__init__("gazebo_chess_arm")
        self.set_parameters([rclpy.parameter.Parameter("use_sim_time", value=True)])
        self._arm = ActionClient(self, FollowJointTrajectory, f"/{config.ARM_CONTROLLER}/follow_joint_trajectory")
        self._grip = ActionClient(self, FollowJointTrajectory, f"/{config.GRIPPER_CONTROLLER}/follow_joint_trajectory")
        self._ik = self.create_client(GetPositionIK, "/compute_ik")
        self._fk = self.create_client(GetPositionFK, "/compute_fk")
        self._js: JointState | None = None
        self.create_subscription(JointState, "/joint_states", self._on_js, 10)

    # ---------- 基础 ----------
    def _on_js(self, msg: JointState) -> None:
        self._js = msg

    def wait_ready(self, timeout: float = 15.0) -> bool:
        ok = (self._arm.wait_for_server(timeout_sec=timeout)
              and self._grip.wait_for_server(timeout_sec=timeout)
              and self._ik.wait_for_service(timeout_sec=timeout))
        self._fk.wait_for_service(timeout_sec=timeout)   # FK 用于复核 IK 解，不强制（缺了退化为信任 IK）
        t0 = time.time()
        while self._js is None and time.time() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.2)
        return ok and self._js is not None

    def current_arm_positions(self) -> dict[str, float]:
        if self._js is None:
            return {}
        return {n: p for n, p in zip(self._js.name, self._js.position)}

    # ---------- IK ----------
    def compute_ik(self, pose: grasp_pose.Pose, timeout_s: float = 1.0) -> list[float] | None:
        """把 link6 的目标位姿（world 帧）解成 6 个臂关节角；解不出返回 None。"""
        (px, py, pz), (qx, qy, qz, qw) = pose
        req = GetPositionIK.Request()
        r = req.ik_request
        r.group_name = config.ARM_GROUP
        r.ik_link_name = config.EEF_LINK
        r.avoid_collisions = True
        r.timeout = Duration(sec=int(timeout_s), nanosec=int((timeout_s % 1) * 1e9))
        # 用当前关节作种子（提高成功率、保持解连续）
        rs = RobotState()
        if self._js is not None:
            rs.joint_state = self._js
        r.robot_state = rs
        ps = PoseStamped()
        ps.header.frame_id = config.PLANNING_FRAME
        ps.pose.position.x, ps.pose.position.y, ps.pose.position.z = px, py, pz
        ps.pose.orientation.x, ps.pose.orientation.y, ps.pose.orientation.z, ps.pose.orientation.w = qx, qy, qz, qw
        r.pose_stamped = ps
        fut = self._ik.call_async(req)
        rclpy.spin_until_future_complete(self, fut, timeout_sec=timeout_s + 2.0)
        res = fut.result()
        if res is None or res.error_code.val != 1:   # 1 = SUCCESS
            return None
        sol = {n: p for n, p in zip(res.solution.joint_state.name, res.solution.joint_state.position)}
        if not all(j in sol for j in ARM_JOINTS):
            return None
        joints = [sol[j] for j in ARM_JOINTS]
        # ⚠️ 实测：这台臂的 IKFast 插件会对**够不着的位姿也返回 error_code=SUCCESS + 一个不匹配的解**。
        # 所以必须用 FK 复核：解出来的关节 FK 回 link6，和请求位姿差太多就判不可达（别让上层拿假解去执行）。
        fk = self._fk_link6(joints)
        if fk is None:
            return joints   # FK 服务不可用时退化为信任 IK（至少别更糟）
        if (abs(fk[0] - px) > 0.02 or abs(fk[1] - py) > 0.02 or abs(fk[2] - pz) > 0.02):
            return None
        return joints

    def _fk_link6(self, joints: list[float]) -> tuple[float, float, float] | None:
        """对一组臂关节角做正运动学，返回 link6 在规划帧的 (x,y,z)。"""
        if not self._fk.service_is_ready():
            return None
        req = GetPositionFK.Request()
        req.header.frame_id = config.PLANNING_FRAME
        req.fk_link_names = [config.EEF_LINK]
        js = JointState()
        js.name = list(ARM_JOINTS)
        js.position = [float(v) for v in joints]
        req.robot_state.joint_state = js
        fut = self._fk.call_async(req)
        rclpy.spin_until_future_complete(self, fut, timeout_sec=3.0)
        res = fut.result()
        if res is None or res.error_code.val != 1 or not res.pose_stamped:
            return None
        p = res.pose_stamped[0].pose.position
        return (p.x, p.y, p.z)

    # ---------- 执行 ----------
    def _send_traj(self, client: ActionClient, joints: list[str], positions: list[float],
                   duration_s: float) -> bool:
        jt = JointTrajectory(joint_names=joints)
        pt = JointTrajectoryPoint(positions=[float(p) for p in positions])
        pt.time_from_start = Duration(sec=int(duration_s), nanosec=int((duration_s % 1) * 1e9))
        jt.points = [pt]
        goal = FollowJointTrajectory.Goal(trajectory=jt)
        f = client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, f, timeout_sec=10.0)
        gh = f.result()
        if gh is None or not gh.accepted:
            return False
        rf = gh.get_result_async()
        rclpy.spin_until_future_complete(self, rf, timeout_sec=duration_s + 8.0)
        return rf.result() is not None

    def goto_arm(self, positions: list[float], duration_s: float = 3.0) -> bool:
        return self._send_traj(self._arm, ARM_JOINTS, positions, duration_s)

    def set_gripper(self, finger_pos: float, duration_s: float = 1.0) -> bool:
        return self._send_traj(self._grip, GRIPPER_JOINTS, [finger_pos, finger_pos], duration_s)

    def open_gripper(self) -> bool:
        return self.set_gripper(config.GRIP_OPEN_M)

    def close_gripper(self) -> bool:
        return self.set_gripper(config.GRIP_CLOSE_M)

    # ---------- 抓 / 放 ----------
    def _solve_candidate(self, approach: grasp_pose.Pose, grasp: grasp_pose.Pose):
        ja = self.compute_ik(approach)
        if ja is None:
            return None
        jg = self.compute_ik(grasp)
        if jg is None:
            return None
        return ja, jg

    def pick_at(self, px: float, py: float, pz: float) -> tuple[bool, str]:
        """在世界点 (px,py,pz) 抓一个子：选一个 IK 可达候选 → 开爪→到接近点→下到抓取点→闭爪→抬回接近点。"""
        for label, approach, grasp in grasp_pose.candidates_for_point(px, py, pz):
            sol = self._solve_candidate(approach, grasp)
            if sol is None:
                continue
            ja, jg = sol
            self.open_gripper()
            if not self.goto_arm(ja, 3.0):
                return False, f"到接近点失败({label})"
            if not self.goto_arm(jg, 2.0):
                return False, f"下到抓取点失败({label})"
            self.close_gripper()
            time.sleep(0.3)
            if not self.goto_arm(ja, 2.0):
                return False, f"抬起失败({label})"
            return True, f"抓取动作完成({label})"
        return False, "所有候选姿态都 IK 不可达"

    def place_at(self, px: float, py: float, pz: float) -> tuple[bool, str]:
        """在世界点放下：到接近点→下到放置点→开爪→抬回接近点。"""
        for label, approach, grasp in grasp_pose.candidates_for_point(px, py, pz):
            sol = self._solve_candidate(approach, grasp)
            if sol is None:
                continue
            ja, jg = sol
            if not self.goto_arm(ja, 3.0):
                return False, f"到放置接近点失败({label})"
            if not self.goto_arm(jg, 2.0):
                return False, f"下到放置点失败({label})"
            self.open_gripper()
            time.sleep(0.3)
            if not self.goto_arm(ja, 2.0):
                return False, f"放后抬起失败({label})"
            return True, f"放置动作完成({label})"
        return False, "放置点所有候选姿态都 IK 不可达"
