# camera

ANIMA 的一个独立「世界」(AWI)：把**真实摄像头**的实时画面交给 ANIMA 看。

这是 ANIMA 第一次看真实物理世界（不再是程序画出来的合成图）。本版定位很轻：**只能看、能聊、不能操作**。

**对大脑只给【看】**：`/perceive`(画面 + 极简 state) 和 `/stream`(MJPEG)。`capabilities` 的 **tools 是空的** —— ANIMA 在这个世界里**没有任何可执行动作**（"只能看、不能操作"是结构上保证的，不是靠提示词约束）。

**摄像头由人来选、来开**：服务启动**不主动打开任何摄像头**，只枚举出电脑上有哪些。打开哪个，由人在世界页下拉框里选——插了多个可随时切换。选中了，画面才出现并传给 ANIMA。

**分辨率可在线调**：选中某摄像头后，世界会用 Linux V4L2 接口问内核这台设备**真支持哪些分辨率**（不写死分辨率表），世界页只给真支持的档供选择。切换分辨率时按该档自动选最优采集格式（同帧率下 YUYV 无损优先，高分辨率下 MJPG 帧率更高会被自动选中）。世界页实时显示摄像头核心参数（**真正生效的**分辨率 / 帧率 / 像素格式，由设备回读），这些也写进 `/perceive` 的 state 交给 ANIMA。

```
cd world/camera && pip install -e . && uvicorn server:app --port 8104
```
打开 `localhost:8104`：在下拉框里选一个摄像头 → 画面出现 → ANIMA（在主界面选 camera 世界）就能看到、能聊。

## 接口

AWI（脑↔世界）：`GET /capabilities`、`GET /perceive`、`POST /invoke`（本世界无动作，一律拒绝）、`GET /health`
人类页/控制（世界本地，不进 AWI）：`GET /stream`、`GET /cameras`、`GET /modes`（当前摄像头真支持的分辨率档）、`POST /select`、`POST /resolution`（切到某支持的分辨率）、`POST /release`、`GET /status`、`GET /`

## 可调项（env，都有默认值）

| env | 默认 | 含义 |
|---|---|---|
| `CAMERA_DEVICE_GLOB` | `/dev/video*` | 枚举摄像头节点的路径模式（平台相关，走发现式） |
| `CAMERA_WIDTH` / `CAMERA_HEIGHT` | `640` / `480` | 默认抓帧分辨率（选中后可在世界页改到设备真支持的任一档） |
| `CAMERA_USABLE_FOURCCS` | `YUYV,MJPG` | 本世界能解码的采集格式（按偏好排序）；设备报的其它格式（如 H264）不放进可选项 |
| `CAMERA_JPEG_QUALITY` | `80` | `/stream` 的 JPEG 画质（1–100） |
| `CAMERA_WARMUP_READS` | `3` | 打开后先丢几帧（等自动曝光收敛） |
| `CAMERA_STREAM_FPS` | `15` | 实时流帧率 |
| `CAMERA_WORLD_VERSION` | `0.3` | 世界版本号 |

## 自测

```
python capture.py            # 仅枚举摄像头，不打开任何设备
python capture.py 0 out.png  # 打开 0 号摄像头抓一帧存 out.png（会真正开硬件）
```
