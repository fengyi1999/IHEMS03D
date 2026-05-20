/**
 * 配置文件 - 系统配置参数
 */

// WebSocket连接配置
const CONFIG = {
    // WebSocket服务器地址
    // 使用HTTP协议连接Socket.IO服务器
    // 修复file://协议下hostname为空的问题
    WS_URL: 'http://' + (window.location.hostname || 'localhost') + ':5002',
    // 调试模式详细日志 (正常模式下关闭)
    DEBUG: false,

    // 备用WebSocket服务器地址（包含局域网IP）
    BACKUP_WS_URLS: [
        'http://' + window.location.hostname + ':5002',
        'http://10.65.171.10:5002',  // 局域网IP地址
        'http://localhost:5002',
        'http://127.0.0.1:5002',
        window.location.origin
    ],

    // 数据更新频率 (毫秒)
    UPDATE_INTERVAL: 1000,

    // 是否启用调试模式 (正常模式下关闭)
    DEBUG: false,

    // Speed模式配置
    SPEED_MODE: {
        // 是否启用speed模式
        ENABLED: false,
        // 当前速度倍数
        MULTIPLIER: 1,
        // 在speed模式下是否调整图表更新频率
        ADJUST_CHART_UPDATE: true,
        // Speed模式下的优化配置
        OPTIMIZATIONS: {
            // 减少图表动画
            REDUCE_ANIMATIONS: true,
            // 限制历史数据点数
            MAX_CHART_POINTS: 100,
            // 批量更新间隔(毫秒)
            BATCH_UPDATE_INTERVAL: 200
        }
    },

    // 图表配置
    CHART: {
        // 数据更新频率 (毫秒)
        UPDATE_INTERVAL: 1000,

        // 是否启用调试模式 (正常模式下关闭)
        DEBUG: false,

        // Speed模式配置
        SPEED_MODE: {
            // 是否启用speed模式
            ENABLED: false,
            // 当前速度倍数
            MULTIPLIER: 1,
            // 在speed模式下是否调整图表更新频率
            ADJUST_CHART_UPDATE: false
        },

        // 图表样式配置
        COLORS: {
            PRIMARY: '#00ff88',
            SECONDARY: '#0088ff',
            WARNING: '#ffaa00',
            DANGER: '#ff4444',
            SUCCESS: '#00ff88',
            INFO: '#00aaff'
        },

        // 数据点数量限制
        MAX_DATA_POINTS: 100,

        // 图表动画配置
        ANIMATION: {
            DURATION: 300,
            EASING: 'linear'
        },

        // 时间轴上显示的数据点数量
        MAX_INTERVAL_DATA_POINTS: 1800,  // 30小时 * 60分钟 = 1800个数据点（累计图表）

        // 参考页面颜色 - 现代化深灰配色方案
        DARK_COLORS: {
            primary: '#3b82f6',   // 主色 - 参考页面蓝色
            success: '#10b981',   // 成功色 - 绿色
            warning: '#f59e0b',   // 警告色 - 橙色
            danger: '#ef4444',    // 危险色 - 红色
            info: '#8b5cf6',      // 信息色 - 紫色
            grid: 'rgba(64, 64, 64, 0.25)',      // 网格线颜色 - 深灰
            text: '#d1d5db',      // 文字颜色
            background: '#2a2a2a', // 背景色 - 改为与区域背景相同
            cardBg: 'rgba(42, 42, 42, 0.8)', // 卡片背景 - 改为与区域背景相同
            border: 'rgba(64, 64, 64, 0.3)', // 边框颜色 - 深灰
            
            // 图表专用颜色 - 国际设计大奖级配色方案
            chartColors: {
                // 参考页面配色方案
                wind: {
                    primary: '#3b82f6',
                    secondary: '#60a5fa',
                    gradient: ['#3b82f6', '#60a5fa', '#93c5fd'],
                    glow: 'rgba(59, 130, 246, 0.3)',
                    // 发电量图表用的淡一点的风电颜色
                    light: '#60a5fa'  // 比primary淡一点
                },
                solar: {
                    primary: '#f59e0b',
                    secondary: '#fbbf24',
                    gradient: ['#f59e0b', '#fbbf24', '#fcd34d'],
                    glow: 'rgba(245, 158, 11, 0.3)'
                },
                storage: {
                    primary: '#8b5cf6',
                    secondary: '#a78bfa',
                    gradient: ['#8b5cf6', '#a78bfa', '#c4b5fd'],
                    glow: 'rgba(139, 92, 246, 0.3)'
                },
                hydrogen: {
                    primary: '#10b981',
                    secondary: '#34d399',
                    gradient: ['#10b981', '#34d399', '#6ee7b7'],
                    glow: 'rgba(16, 185, 129, 0.3)',
                    // 制氢量图表用的淡一点的制氢颜色
                    light: '#34d399'  // 比primary淡一点
                },
                grid: {
                    primary: '#ef4444',
                    secondary: '#f87171',
                    gradient: ['#ef4444', '#f87171', '#fca5a5'],
                    glow: 'rgba(239, 68, 68, 0.3)'
                },
                
                // 生产数据专用配色
                production: {
                    primary: '#06b6d4',
                    secondary: '#0891b2',
                    gradient: ['#06b6d4', '#0891b2', '#0e7490'],
                    glow: 'rgba(6, 182, 212, 0.3)'
                },
                
                // 利用率专用配色
                utilization: {
                    wind: '#0ea5e9',
                    solar: '#f59e0b',
                    combined: '#8b5cf6'
                },
                
                // 高级渐变色（用于面积图）
                windGradient: [
                    { offset: 0, color: 'rgba(14, 165, 233, 0.9)' },
                    { offset: 0.5, color: 'rgba(56, 189, 248, 0.6)' },
                    { offset: 1, color: 'rgba(125, 211, 252, 0.2)' }
                ],
                solarGradient: [
                    { offset: 0, color: 'rgba(245, 158, 11, 0.9)' },
                    { offset: 0.5, color: 'rgba(251, 191, 36, 0.6)' },
                    { offset: 1, color: 'rgba(253, 224, 71, 0.2)' }
                ],
                storageGradient: [
                    { offset: 0, color: 'rgba(16, 185, 129, 0.9)' },
                    { offset: 0.5, color: 'rgba(52, 211, 153, 0.6)' },
                    { offset: 1, color: 'rgba(110, 231, 183, 0.2)' }
                ],
                hydrogenGradient: [
                    { offset: 0, color: 'rgba(6, 182, 212, 0.9)' },
                    { offset: 0.5, color: 'rgba(34, 211, 238, 0.6)' },
                    { offset: 1, color: 'rgba(103, 232, 249, 0.2)' }
                ],
                gridGradient: [
                    { offset: 0, color: 'rgba(139, 92, 246, 0.9)' },
                    { offset: 0.5, color: 'rgba(167, 139, 250, 0.6)' },
                    { offset: 1, color: 'rgba(196, 181, 253, 0.2)' }
                ]
            }
        }
    },

    // 数据刷新配置 (正常模式下统一为每秒1次)
    DATA_REFRESH: {
        // 主页面数据刷新间隔(毫秒)
        MAIN_PAGE_INTERVAL: 1000,
        // 能量管理页面数据刷新间隔(毫秒) - 正常模式下改为1秒
        ENERGY_PAGE_INTERVAL: 1000,
        // 系统分析页面数据刷新间隔(毫秒)
        ANALYSIS_PAGE_INTERVAL: 1000,
        // 报表管理页面数据刷新间隔(毫秒)
        REPORT_PAGE_INTERVAL: 5000
    }
};
