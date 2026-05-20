<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Flask-2.3.2-green.svg" alt="Flask">
  <img src="https://img.shields.io/badge/Vue.js-2.x-brightgreen.svg" alt="Vue.js">
  <img src="https://img.shields.io/badge/WebSocket-Real--time-orange.svg" alt="WebSocket">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey.svg" alt="License">
</p>

<h1 align="center">⚡ IHEMS03D — 智慧绿氢管理系统</h1>
<h3 align="center">Intelligent Hydrogen Energy Management System</h3>

<p align="center">
  <b>中文</b> | <a href="#english">English</a>
</p>

---

## 📖 项目简介

**IHEMS03D** 是一套面向绿氢制备场景的智慧能源管理系统，实现了从 **Simulink 仿真模型** → **TCP 实时数据采集** → **后端处理与存储** → **WebSocket 实时推送** → **前端可视化大屏** 的完整数据链路。

系统支持 20 个电力/氢能关键变量的实时监控、历史数据归档、聚合统计分析，并提供现代化暗色主题仪表盘。

### 🏗️ 系统架构

```
┌──────────────┐     TCP(14001)     ┌─────────────────┐     WebSocket(5002)     ┌──────────────┐
│  Simulink /   │ ────────────────→ │  Backend (Flask) │ ──────────────────────→ │  Frontend    │
│  Simsend 模拟器 │  20 变量实时数据    │  + SQLite DB     │    JSON 实时推送        │  (Vue.js)    │
└──────────────┘                    └─────────────────┘                         └──────────────┘
```

### ✨ 核心功能

| 模块 | 功能 |
|------|------|
| 🔌 **TCP 接收器** | 接收 Simulink 模型通过 TCP 发送的 20 维实时数据 |
| 📡 **WebSocket 服务** | 将后端处理结果实时推送至前端，支持局域网多端访问 |
| 🗄️ **数据管理** | SQLite 存储 + 自动归档 + 每日聚合统计 |
| 📊 **可视化大屏** | 暗色主题统一仪表盘，含功率/电压/电流/效率/SOC 等图表 |
| 🧪 **仿真测试** | 内置 Simsend2/3 模拟器，无需 Simulink 即可运行 |
| ⚙️ **灵活配置** | CLI 参数控制端口、数据库、模拟模式等 |

---

## 🚀 快速开始

### 环境要求

- Python 3.8+
- Windows / Linux（WSL 支持）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动系统

```bash
# 完整启动（后端 + 自动打开前端仪表盘）
python run.py

# 不自动打开浏览器
python run.py --no-browser

# 自定义端口
python run.py --tcp-port 15001 --ws-port 5003
```

### 3. 模拟测试（无需 Simulink）

另开一个终端，运行数据模拟器：

```bash
python Simsend3.py
```

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--tcp-port` | 14001 | TCP 数据接收端口 |
| `--ws-port` | 5002 | WebSocket 服务端口 |
| `--no-browser` | - | 不自动打开浏览器 |
| `--no-db` | - | 不使用数据库（纯内存模式） |
| `--no-save` | - | 不保存接收到的数据 |

---

## 📁 项目结构

```
IHEMS03D/
├── run.py                     # 主启动脚本（CLI 参数、进程管理）
├── Simsend2.py / Simsend3.py  # Simulink 数据模拟器（测试用）
├── requirements.txt           # Python 依赖
│
├── backend/
│   ├── app.py                 # Flask 应用入口 + 能源管理系统主类
│   ├── config.py              # 系统配置（端口、变量名、数据库）
│   ├── simulink_receiver.py   # TCP 数据接收器
│   ├── websocket_server.py    # WebSocket 实时推送服务
│   ├── db_manager.py          # SQLite 数据库管理（归档/聚合）
│   ├── chart_generator.py     # 图表数据生成器
│   └── data/                  # SQLite 数据库文件
│
└── frontend/
    ├── index.html             # 仪表盘主页 (Vue.js + Element UI)
    ├── css/                   # 暗色主题样式
    │   ├── dark-theme.css
    │   ├── unified-dashboard.css
    │   └── power-colors.css
    └── js/                    # 前端逻辑
        ├── charts.js          # ECharts 图表配置
        ├── config.js          # 前端参数配置
        └── main.js            # Vue 主入口
```

---

## 📊 监控变量

系统实时追踪 20 个关键参数：

`power` · `voltage` · `current` · `frequency` · `active_power` · `reactive_power` · `power_factor` · `temperature` · `humidity` · `pressure` · `flow_rate` · `efficiency` · `soc` · `carbon_reduction` · `energy_saved` · `production` · `consumption` · `grid_load` · `battery_voltage` · `battery_current`

---

## 🔧 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Flask 2.3 + Flask-SocketIO |
| 实时通信 | WebSocket (python-socketio) |
| 数据库 | SQLite |
| 前端框架 | Vue.js 2.x + Element UI |
| 图表 | ECharts |
| 数据处理 | NumPy |
| 仿真接口 | TCP Socket (raw binary) |

---

## 📝 License

MIT

---

<a name="english"></a>

# ⚡ IHEMS03D — Intelligent Hydrogen Energy Management System

## 📖 Overview

**IHEMS03D** is a smart energy management system designed for green hydrogen production scenarios. It implements a complete data pipeline: **Simulink Model** → **TCP Real-time Acquisition** → **Backend Processing & Storage** → **WebSocket Live Push** → **Frontend Visualization Dashboard**.

The system monitors 20 key power/hydrogen variables in real time, supports historical data archiving and aggregated statistical analysis, and features a modern dark-themed unified dashboard.

### 🏗️ Architecture

```
┌──────────────┐     TCP(14001)     ┌─────────────────┐     WebSocket(5002)     ┌──────────────┐
│  Simulink /   │ ────────────────→ │  Backend (Flask) │ ──────────────────────→ │  Frontend    │
│  Simsend Sim  │  20-var realtime  │  + SQLite DB     │    JSON push           │  (Vue.js)    │
└──────────────┘                    └─────────────────┘                         └──────────────┘
```

### ✨ Key Features

| Module | Description |
|--------|-------------|
| 🔌 **TCP Receiver** | Receives 20-dimension realtime data from Simulink via TCP |
| 📡 **WebSocket Server** | Pushes processed data to frontend in real time (LAN accessible) |
| 🗄️ **Data Management** | SQLite storage + auto archiving + daily aggregated statistics |
| 📊 **Dashboard** | Dark-themed unified dashboard with charts for power, voltage, SOC, etc. |
| 🧪 **Simulation** | Built-in Simsend2/3 simulators for testing without Simulink |
| ⚙️ **Flexible Config** | CLI arguments for ports, database mode, simulation, etc. |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Windows / Linux (WSL compatible)

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Launch

```bash
# Full launch (backend + auto-open dashboard)
python run.py

# Headless mode
python run.py --no-browser

# Custom ports
python run.py --tcp-port 15001 --ws-port 5003
```

### 3. Test with Simulator

In another terminal:

```bash
python Simsend3.py
```

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--tcp-port` | 14001 | TCP data receiving port |
| `--ws-port` | 5002 | WebSocket server port |
| `--no-browser` | - | Don't auto-open browser |
| `--no-db` | - | In-memory mode (no database) |
| `--no-save` | - | Don't persist received data |

---

## 📁 Project Structure

```
IHEMS03D/
├── run.py                     # Main launcher (CLI args, process manager)
├── Simsend2.py / Simsend3.py  # Simulink data simulators (testing)
├── requirements.txt           # Python dependencies
│
├── backend/
│   ├── app.py                 # Flask entry + EnergyManagementSystem core
│   ├── config.py              # System config (ports, variables, DB)
│   ├── simulink_receiver.py   # TCP data receiver
│   ├── websocket_server.py    # WebSocket realtime push service
│   ├── db_manager.py          # SQLite DB manager (archive/aggregate)
│   ├── chart_generator.py     # Chart data generator
│   └── data/                  # SQLite database files
│
└── frontend/
    ├── index.html             # Dashboard (Vue.js + Element UI)
    ├── css/                   # Dark theme stylesheets
    └── js/                    # Frontend logic (ECharts, Vue)
```

---

## 📊 Monitored Variables

20 key parameters tracked in real time:

`power` · `voltage` · `current` · `frequency` · `active_power` · `reactive_power` · `power_factor` · `temperature` · `humidity` · `pressure` · `flow_rate` · `efficiency` · `soc` · `carbon_reduction` · `energy_saved` · `production` · `consumption` · `grid_load` · `battery_voltage` · `battery_current`

---

## 🔧 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask 2.3 + Flask-SocketIO |
| Realtime | WebSocket (python-socketio) |
| Database | SQLite |
| Frontend | Vue.js 2.x + Element UI |
| Charts | ECharts |
| Data Processing | NumPy |
| Simulation I/O | TCP Socket (raw binary) |

---

## 📝 License

MIT © 2025
