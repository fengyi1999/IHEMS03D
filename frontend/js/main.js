/**
 * 主脚本文件 - 三一智慧绿氢管理系统
 */

// 数据存储
const APP_DATA = {
    socket: null,         // WebSocket连接对象
    connected: false,     // 连接状态
    dataHistory: [],      // 历史数据
    latestData: {},       // 最新数据
    systemStatus: '未连接', // 系统状态
    useSimulation: false  // 是否使用模拟数据，默认为false
};

// 新增：用于功率曲线图的分钟级数据
const MINUTE_POWER_DATA = {
    timestamps: [],
    wind_power: [],
    solar_power: [],
    storage_power: [],
    hydrogen_power: [],
    grid_power: [],
};
let secondCounter = 0;
let tempPowerData = {
    wind_power: 0,
    solar_power: 0,
    storage_power: 0,
    hydrogen_power: 0,
    grid_power: 0,
    count: 0
};

// 注册 Vue Multiselect 组件
if (window.VueMultiselect) {
    Vue.component('multiselect', window.VueMultiselect.default);
    console.log('Vue Multiselect 组件已成功注册');
} else {
    console.error('Vue Multiselect 组件加载失败，请检查脚本引入');
}

// Vue应用实例
const app = new Vue({
    el: '#app',
    data: {
        currentTime: '',      // 当前时间
        simulationTime: '',   // 仿真时间
        simulationSpeed: 1,   // 仿真速度倍数
        aggregationInfo: { minutes: 1, count: 0 }, // 新增：聚合信息
        simulationStartTime: null, // 仿真开始时间
        latestData: APP_DATA.latestData,  // 最新数据
        systemStatus: APP_DATA.systemStatus,  // 系统状态
        currentPage: 1,       // 当前页面，默认显示系统页面
        charts: {},
        showSettings: false,
        systemInfo: {         // 系统信息区域数据
            hydrogen_power: 0,       // 制氢功率 (MW)
            production_rate: 0,      // 产氢速率 (Nm³/h)
            energy_consumption: 0,   // 制氢能耗 (MWh/Nm³)
            total_production: 0      // 累计产氢量 (Nm³)
        },
        deviceStats: {        // 设备状态统计区域数据
            running_count: 0,        // 运行数量
            standby_count: 0,        // 待机数量
            shutdown_count: 0,       // 停机数量
            maintenance_count: 0,    // 检修数量
            cold_start_count: 0,     // 冷启动数量
            hot_start_count: 0,      // 热启动数量
            idle_count: 0            // 待命数量
        },

        // WebSocket连接
        socket: null,
        socketConnected: false,

        // 数据分析页面数据
        variables: [],                // 变量列表
        selectedVariables: [],        // 选中的变量
        timeRange: '1h',              // 时间范围
        startTime: '',                // 自定义开始时间
        endTime: '',                  // 自定义结束时间
        variableData: [],             // 变量数据
        dataLoading: false,           // 数据加载状态
        variableChart: null,          // 变量图表对象
        chartOption: null,            // 图表配置
        resizeChartHandler: null,     // 图表大小调整处理函数

        // 报表分析页面数据
        selectedReportVariables: [],  // 报表选中的变量
        reportTimeRange: '1h',        // 报表时间范围
        reportStartTime: '',          // 报表自定义开始时间
        reportEndTime: '',            // 报表自定义结束时间
        reportData: [],               // 报表数据
        reportLoading: false,         // 报表数据加载状态
        reportError: null,            // 报表错误信息
        reportTimeout: null,         // 报表请求超时计时器
    },
    computed: {
        // 计算累积光伏发电量
        totalSolarEnergy() {
            if (!this.latestData.data) return 0;
            // 光伏发电量应该是光伏功率的积分，数值应该远大于下网电量
            // 如果后端提供了solar_energy字段，直接使用；否则返回0
            return this.latestData.data.solar_energy || 0;
        },
        
        // 计算累积下网电量
        totalGridImportEnergy() {
            if (!this.latestData.data) return 0;
            // 总下网电量应该是下网功率的积分
            return this.latestData.data.grid_import_energy || 0;
        }
    },
    methods: {
        // 计算下网电量（根据时间单位和功率）
        calculateGridImportEnergy(data) {
            if (!data || !data.grid_power) return 0;
            
            // 获取当前时间单位（分钟）
            const timeUnitMinutes = this.aggregationInfo.minutes || 15;
            
            // 如果是下网功率（正值表示下网）
            const gridPower = data.grid_power > 0 ? data.grid_power : 0;
            
            // 计算当前时间段的电量：功率(MW) * 时间(小时) = 电量(MWh)
            const currentEnergy = gridPower * (timeUnitMinutes / 60);
            
            return currentEnergy;
        },

        // 计算光伏预测功率（4个时间单位的平滑）
        calculateSolarForecast(data) {
            if (!data || !data.solar_power) return 0;
            
            // 维护一个滑动窗口存储最近4个时间单位的光伏功率
            if (!this.solarPowerHistory) {
                this.solarPowerHistory = [];
            }
            
            this.solarPowerHistory.push(data.solar_power);
            
            // 保持最多4个数据点
            if (this.solarPowerHistory.length > 4) {
                this.solarPowerHistory.shift();
            }
            
            // 计算平均值作为预测功率
            const sum = this.solarPowerHistory.reduce((a, b) => a + b, 0);
            return sum / this.solarPowerHistory.length;
        },

        // 计算氢气产量（累计值，使用新公式：累加（制氢功率/制氢能效/4））
        calculateHydrogenProduction(data) {
            if (!data) return '0.00';
            
            // 使用新的氢气产量公式：累加（制氢功率/制氢能效/4）
            // 如果后端已经按照新公式计算了total_production，直接使用并转换为吨
            if (data.total_production !== undefined && data.total_production > 0) {
                const hydrogenMassTons = data.total_production / 11123; // 从标方转换为吨
                return hydrogenMassTons.toFixed(3);
            }
            
            // 如果没有total_production，尝试根据当前数据计算
            if (data.hydrogen_power && data.energy_consumption && data.energy_consumption > 0) {
                // 当前时间段的氢气产量 = 制氢功率 / 制氢能效 / 4
                const currentProduction = data.hydrogen_power / data.energy_consumption / 4;
                
                // 这里应该累加，但由于没有历史累加数据，只能显示当前值
                const hydrogenMassTons = currentProduction / 11123; // 从标方转换为吨
                return hydrogenMassTons.toFixed(3);
            }
            
            return '0.00';
        },
        
        // 获取储氢SOH（从储氢状态读取）
        getStorageSOH(data) {
            if (!data) return 0;
            
            // 从后端数据中读取储氢SOH数值，显示为0-100的整数
            if (data.hydrogen_soc !== undefined) {
                // 如果数据是0-1的小数，转换为0-100的整数
                if (data.hydrogen_soc <= 1) {
                    return data.hydrogen_soc * 100;
                }
                // 如果数据已经是0-100的范围，直接返回
                return data.hydrogen_soc;
            }
            
            // 如果没有储氢SOH数据，返回默认值
            return 0;
        },
        
        // 获取供氢速率（从储氢状态读取）
        getHydrogenSupplyRate(data) {
            if (!data) return 0;
            
            // 从后端数据中读取储氢罐充放氢气速率，取绝对值
            if (data.hydrogen_hss !== undefined) {
                return Math.abs(data.hydrogen_hss);
            }
            
            // 如果没有供氢速率数据，返回默认值
            return 0;
        },

        // 计算下网电量（使用总下网电量）
        calculateGridImportEnergyTotal(data) {
            if (!data) return 0;
            
            // 直接使用后端提供的总下网电量
            return data.grid_import_energy || 0;
        },

        // 格式化数字，添加千位分隔符
        formatNumber(num) {
            if (num === undefined || num === null) return '0';
            return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
        },

        // 格式化运行时间，将秒数转换为小时、分钟和秒
        formatRuntime(seconds) {
            if (seconds === undefined || seconds === null) return '00时00分00秒';
            
            // 确保 seconds是数字类型
            let totalSeconds = parseInt(seconds) || 0;
            
            // 在speed模式下，运行时间需要乘以speed倍数
            if (this.simulationSpeed > 1) {
                totalSeconds = Math.floor(totalSeconds * this.simulationSpeed);
            }
            
            const hours = Math.floor(totalSeconds / 3600);
            const minutes = Math.floor((totalSeconds % 3600) / 60);
            const remainingSeconds = Math.floor(totalSeconds % 60);
            
            // 格式化为两位数，从00时00分00秒开始
            const formattedHours = hours.toString().padStart(2, '0');
            const formattedMinutes = minutes.toString().padStart(2, '0');
            const formattedSeconds = remainingSeconds.toString().padStart(2, '0');
            
            return `${formattedHours}时${formattedMinutes}分${formattedSeconds}秒`;
        },

        /**
         * 获取格式化的数值，当无数据时显示"-"
         * @param {Object} data - 数据对象
         * @param {String} field - 字段名
         * @param {Number} index - 数组索引
         * @param {Number} decimals - 小数位数
         * @returns {String} 格式化后的值
         */
        getFormattedValue(data, field, index, decimals) {
            // 调试输出
            if (field === 'electrolyzer_real_power') {
                console.log(`getFormattedValue - ${field}[${index}]:`, data && data[field] ? data[field][index] : 'undefined');

                // 获取电解槽状态
                const status = data && data['electrolyzer_status'] ? data['electrolyzer_status'][index] : -1;
                console.log(`getFormattedValue - 电解槽 #${index+1} 状态:`, status);
            }

            if (!data || !data[field] || data[field][index] === null || data[field][index] === undefined) {
                return "-";
            }

            const value = data[field][index];

            // 检查值是否为有效数字
            if (isNaN(value)) {
                console.error(`getFormattedValue - ${field}[${index}] 值无效:`, value);
                return "-";
            }

            try {
                return this.formatNumber(value.toFixed(decimals));
            } catch (error) {
                console.error(`getFormattedValue - 格式化 ${field}[${index}] 时出错:`, error);
                return "-";
            }
        },

        /**
         * 获取电解槽状态的CSS类名
         * @param {Object} data - 数据对象
         * @param {String} field - 字段名
         * @param {Number} index - 数组索引
         * @returns {String} CSS类名
         */
        getStatusClass(data, field, index) {
            if (!data || !data[field] || data[field][index] === null || data[field][index] === undefined) {
                return 'unknown';
            }

            const status = data[field][index];
            // 根据新的状态值定义：
            // 状态值 0 表示检修
            // 状态值 1 表示冷备待机
            // 状态值 2 3 4 均表示冷启动
            // 状态值 5 表示热备
            // 状态值 6 表示热启动
            // 状态值 7 表示运行
            switch (status) {
                case 0: return 'maintenance';
                case 1: return 'standby';       // 冷备待机
                case 2:
                case 3:
                case 4: return 'cold-start';    // 冷启动
                case 5: return 'hot-standby';   // 热备
                case 6: return 'hot-start';     // 热启动
                case 7: return 'running';       // 运行
                default: return 'unknown';
            }
        },

        /**
         * 获取电解槽状态的文本描述
         * @param {Object} data - 数据对象
         * @param {String} field - 字段名
         * @param {Number} index - 数组索引
         * @returns {String} 状态文本
         */
        getStatusText(data, field, index) {
            if (!data || !data[field] || data[field][index] === null || data[field][index] === undefined) {
                return "-";
            }

            const status = data[field][index];
            // 根据新的状态值定义：
            // 状态值 0 表示检修
            // 状态值 1 表示冷备待机
            // 状态值 2 3 4 均表示冷启动
            // 状态值 5 表示热备
            // 状态值 6 表示热启动
            // 状态值 7 表示运行
            switch (status) {
                case 0: return '检修';
                case 1: return '冷备待机';
                case 2:
                case 3:
                case 4: return '冷启动';
                case 5: return '热备';
                case 6: return '热启动';
                case 7: return '运行';
                default: return '未知';
            }
        },

        /**
         * 获取进度条宽度
         * @param {Object} data - 数据对象
         * @param {String} field - 字段名
         * @param {Number} index - 数组索引
         * @returns {String} 进度条宽度百分比
         */
        getProgressBarWidth(data, field, index) {
            // 调试输出
            console.log(`getProgressBarWidth - ${field}[${index}]:`, data && data[field] ? data[field][index] : 'undefined');

            if (!data || !data[field] || data[field][index] === null || data[field][index] === undefined) {
                return '0%';
            }

            // 获取电解槽状态
            const status = data['electrolyzer_status'] ? data['electrolyzer_status'][index] : -1;
            console.log(`电解槽 #${index+1} 状态:`, status);

            // 根据新的状态值定义，只有在运行(7)、冷启动(2,3,4)或热启动(6)状态下才显示进度条
            if (status !== 7 && status !== 2 && status !== 3 && status !== 4 && status !== 6) {
                return '0%';
            }

            // 获取实际功率
            const power = data[field][index];

            // 检查功率值是否有效
            if (power === null || power === undefined || isNaN(power)) {
                console.error(`电解槽 #${index+1} 功率无效:`, power);
                return '0%';
            }

            console.log(`电解槽 #${index+1} 功率:`, power, 'MW');

            // 最大功率为5MW
            const maxPower = 5;

            // 计算百分比，最大不超过100%
            const percentage = Math.min(100, (power / maxPower) * 100);
            console.log(`电解槽 #${index+1} 进度条百分比:`, percentage, '%');

            return percentage + '%';
        },

        /**
         * 获取电解槽产氢速率
         * @param {Object} data - 数据对象
         * @param {String} field - 字段名
         * @param {Number} index - 数组索引
         * @returns {String} 产氢速率
         */
        getHydrogenRate(data, field, index) {
            if (!data || !data[field] || data[field][index] === null || data[field][index] === undefined) {
                return "0.0";
            }

            // 直接使用hydrogen_rate数据，与后端保持一致
            if (data['hydrogen_rate'] && data['hydrogen_rate'][index] !== undefined) {
                const rate = data['hydrogen_rate'][index];
                return this.formatNumber(rate.toFixed(1));
            }

            // 如果没有单独的产氢速率数据，则使用给定的字段
            const value = data[field][index];
            return this.formatNumber(value.toFixed(1));
        },

        /**
         * 计算电解槽能耗
         * @param {Object} data - 数据对象
         * @param {String} powerField - 功率字段名
         * @param {String} rateField - 产氢速率字段名
         * @param {Number} index - 数组索引
         * @returns {String} 格式化后的能耗（不带单位，紧凑格式）
         */
        getEnergyConsumption(data, powerField, rateField, index) {
            if (!data || !data[powerField] || !data[rateField] ||
                data[powerField][index] === null || data[powerField][index] === undefined ||
                data[rateField][index] === null || data[rateField][index] === undefined) {
                return '0.0';
            }

            // 获取实际功率（MW）和产氢速率（Nm³/h）
            const power = data[powerField][index]; // MW
            const rate = data[rateField][index];   // Nm³/h

            // 如果功率或产氢率非常接近于0，则认为能耗为0，以避免除零错误
            if (power < 0.001 || rate < 0.01) {
                return '0.0';
            }

            // 计算能耗（kWh/Nm³）= 功率(MW) * 1000 / 产氢速率(Nm³/h)
            const consumption = (power * 1000) / rate;

            return consumption.toFixed(1);
        },

        /**
         * 获取系统信息
         * @param {Object} data - 数据对象
         * @returns {Object} 系统信息
         */
        getSystemInfo(data) {
            if (!data || !data['system_info']) {
                return {};
            }
            return data['system_info'];
        },

        /**
         * 获取设备状态统计
         * @param {Object} data - 数据对象
         * @returns {Object} 设备状态统计
         */
        getDeviceStats(data) {
            if (!data || !data['device_stats']) {
                return {};
            }
            return data['device_stats'];
        },

        // 切换页面
        switchPage(pageIndex) {
            // 销毁原页面的效果
            if (this.currentPage === 1 && pageIndex !== 1) {
                // 如果从首页切换到其他页面，销毁Matrix效果
                this.destroyMatrixRain();
            }
            
            // 清理页面特定的定时器
            if (this.pageUpdateInterval) {
                clearInterval(this.pageUpdateInterval);
                this.pageUpdateInterval = null;
            }
            
            // 更新当前页面
            this.currentPage = pageIndex;

            // 如果切换到首页，初始化Matrix雨效果
            if (pageIndex === 1) {
                // 延迟一下，确保DOM已更新
                setTimeout(() => {
                    this.initMatrixRain(); // 初始化首页Matrix雨效果
                }, 100);
            }
            
            // 如果切换到能量管理页面，初始化能量管理相关图表
            if (pageIndex === 2) {
                // 延迟一下，确保DOM已更新
                setTimeout(() => {
                    initCharts(); // 初始化能量管理页面的所有图表
                }, 100);
                
                // 设置能量管理页面的快速刷新
                this.pageUpdateInterval = setInterval(() => {
                    this.$forceUpdate();
                }, CONFIG.DATA_REFRESH.ENERGY_PAGE_INTERVAL);
            }
            
            // 根据页面设置不同的数据刷新频率
            if (pageIndex === 3) { // 系统分析页面
                this.pageUpdateInterval = setInterval(() => {
                    this.$forceUpdate();
                }, CONFIG.DATA_REFRESH.ANALYSIS_PAGE_INTERVAL);
            } else if (pageIndex === 4) { // 报表管理页面
                this.pageUpdateInterval = setInterval(() => {
                    this.$forceUpdate();
                }, CONFIG.DATA_REFRESH.REPORT_PAGE_INTERVAL);
            }
        },

        // 重新连接WebSocket
        reconnectWebSocket() {
            if (APP_DATA.socket) {
                APP_DATA.socket.close();
                initWebSocket();
            }
        },

        // 更新当前时间
        updateTime() {
            const now = new Date();
            const dateOptions = { year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'long' };
            const timeOptions = { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
            
            const dateStr = now.toLocaleDateString('zh-CN', dateOptions);
            const timeStr = now.toLocaleTimeString('zh-CN', timeOptions);
            
            // 在speed模式下，在真实时间前显示速度标识
            if (this.simulationSpeed > 1) {
                this.currentTime = `X${this.simulationSpeed} ${dateStr} ${timeStr}`;
            } else {
                this.currentTime = dateStr + ' ' + timeStr;
            }
            
            // 在speed模式下不需要单独的仿真时间，因为数据按真实时间显示
            // 但数据接收频率会增加
            if (this.simulationSpeed > 1) {
                // 显示speed模式信息
                const speedEl = document.getElementById('simulation-speed');
                const timeEl = document.getElementById('simulation-time');
                const infoEl = document.getElementById('simulation-info');
                
                if (speedEl && timeEl && infoEl) {
                    speedEl.textContent = `仿真速度: ${this.simulationSpeed}倍`;
                    timeEl.textContent = `时间: ${dateStr} ${timeStr}`;
                    infoEl.style.display = 'block';
                }
            } else {
                const infoEl = document.getElementById('simulation-info');
                if (infoEl) {
                    infoEl.style.display = 'none';
                }
            }
        },

        // ===== 数据分析页面方法 =====

        // 填充变量列表（修复内部语法）
        populateVariables() {
            const variablesList = [
                // 系统信息
                { group: '系统信息', name: 'grid_power', label: '电网功率 (MW)' },
                { group: '系统信息', name: 'grid_export_power', label: '电网输出功率 (MW)' },
                { group: '系统信息', name: 'grid_import_power', label: '电网输入功率 (MW)' },
                { group: '系统信息', name: 'grid_voltage', label: '电网电压 (V)' },
                { group: '系统信息', name: 'grid_frequency', label: '电网频率 (Hz)' },
                { group: '系统信息', name: 'solar_power', label: '光伏功率 (MW)' },
                { group: '系统信息', name: 'wind_power', label: '风电功率 (MW)' },
                { group: '系统信息', name: 'storage_power', label: '储能功率 (MW)' },
                { group: '系统信息', name: 'hydrogen_real_power', label: '制氢实际功率 (MW)' },
                { group: '系统信息', name: 'hydrogen_set_power', label: '制氢设定功率 (MW)' },
                { group: '系统信息', name: 'hydrogen_production', label: '产氢速率 (Nm³/h)' },
                { group: '系统信息', name: 'renewable_utilization', label: '可再生能源利用率 (%)' },
                { group: '系统信息', name: 'green_energy_ratio', label: '绿电比例 (%)' },
                { group: '系统信息', name: 'system_runtime', label: '系统运行时间 (h)' },
                { group: '系统信息', name: 'wind_utilization_rate', label: '风电利用率 (%)' },
                { group: '系统信息', name: 'solar_utilization_rate', label: '光伏利用率 (%)' },
                { group: '系统信息', name: 'energy_consumption', label: '制氢能耗 (kWh/Nm³)' }
            ];

            // 添加电解槽变量
            for (let i = 1; i <= 20; i++) {
                variablesList.push({ group: '电解槽', name: `electrolyzer_status_${i}`, label: `电解槽${i}状态` });
                variablesList.push({ group: '电解槽', name: `electrolyzer_set_power_${i}`, label: `电解槽${i}设定功率 (MW)` });
                variablesList.push({ group: '电解槽', name: `electrolyzer_real_power_${i}`, label: `电解槽${i}实际功率 (MW)` });
                variablesList.push({ group: '电解槽', name: `hydrogen_rate_${i}`, label: `电解槽${i}产氢速率 (Nm³/h)` });
                variablesList.push({ group: '电解槽', name: `electrolyzer_temp_${i}`, label: `电解槽${i}温度 (°C)` });
            }
            
            // 添加带点号变量支持（兼容性）
            for (let i = 0; i < 20; i++) {
                variablesList.push({ group: '电解槽（兼容）', name: `electrolyzer_status.${i}`, label: `电解槽${i+1}状态(兼容)` });
                variablesList.push({ group: '电解槽（兼容）', name: `electrolyzer_set_power.${i}`, label: `电解槽${i+1}设定功率(兼容) (MW)` });
                variablesList.push({ group: '电解槽（兼容）', name: `electrolyzer_real_power.${i}`, label: `电解槽${i+1}实际功率(兼容) (MW)` });
                variablesList.push({ group: '电解槽（兼容）', name: `hydrogen_rate.${i}`, label: `电解槽${i+1}产氢速率(兼容) (Nm³/h)` });
                variablesList.push({ group: '电解槽（兼容）', name: `electrolyzer_temp.${i}`, label: `电解槽${i+1}温度(兼容) (°C)` });
            }
            
            this.variables = variablesList;
            console.log('变量列表已填充:', this.variables.length);
        },

        // 清除变量选择
        clearVariables() {
            this.selectedVariables = [];
            if (this.variableChart) {
                this.variableChart.dispose();
                this.variableChart = null;
            }
            this.variableData = [];
        },

        // 加载变量数据
        loadVariableData() {
            if (!this.socket) {
                console.error('WebSocket未连接');
                return;
            }
            
            if (!this.selectedVariables || this.selectedVariables.length === 0) {
                console.warn('请选择至少一个变量');
                return;
            }

            this.dataLoading = true;
            this.variableData = []; // 清除旧数据

            // 准备时间范围
            let startTime = null;
            let endTime = null;

            if (this.timeRange === 'custom') {
                startTime = this.startTime ? Math.floor(new Date(this.startTime).getTime() / 1000) : null;
                endTime = this.endTime ? Math.floor(new Date(this.endTime).getTime() / 1000) : Math.floor(Date.now() / 1000);
            } else {
                // 预设时间范围
                const now = Math.floor(Date.now() / 1000);
                endTime = now;

                switch (this.timeRange) {
                    case '5m': startTime = now - 5 * 60; break;
                    case '15m': startTime = now - 15 * 60; break;
                    case '30m': startTime = now - 30 * 60; break;
                    case '1h': startTime = now - 60 * 60; break;
                    case '6h': startTime = now - 6 * 60 * 60; break;
                    case '12h': startTime = now - 12 * 60 * 60; break;
                    case '24h': startTime = now - 24 * 60 * 60; break;
                    default: startTime = now - 60 * 60; // 默认1小时
                }
            }

            // 准备请求数据
            const variableNames = this.selectedVariables.map(v => v.name);
            
            const requestData = {
                variable_names: variableNames,
                start_time: startTime,
                end_time: endTime,
                use_chart: true
            };

            console.log('发送变量数据请求:', requestData);
            
            // 发送请求到服务器
            this.socket.emit('get_variable_data', JSON.stringify(requestData));
        },

        // 解析数值
        parseNumericValue(value) {
            if (value === null || value === undefined || value === '') {
                return null;
            }
            if (typeof value === 'number') {
                return value;
            }
            if (typeof value === 'string') {
                const parsed = parseFloat(value);
                return isNaN(parsed) ? null : parsed;
            }
            return null;
        },

        // 渲染 ECharts 图表
        renderEChart(option) {
            const chartContainer = document.getElementById('variable-chart-container');
            if (!chartContainer) {
                console.error('图表容器 #variable-chart-container 未找到');
                return;
            }

            try {
                // 先销毁旧图表实例
                if (this.variableChart) {
                    try {
                        this.variableChart.dispose();
                    } catch (e) {
                        console.warn('销毁旧图表实例出错', e);
                    }
                    this.variableChart = null;
                }
                
                // 确保容器可见并适应flexbox布局
                chartContainer.style.display = 'block';
                
                // 创建新图表
                this.variableChart = echarts.init(chartContainer);
                
                // 修改图表配置，优化显示效果
                if (option) {
                    // 优化图表区域的网格配置
                    if (option.grid) {
                        // 设置图表区域边距，减少空白，增大图表显示范围
                        option.grid.left = '2%';
                        option.grid.right = '2%';
                        option.grid.top = '50px';
                        option.grid.bottom = '50px';
                        option.grid.containLabel = true;
                    }
                    
                    // 优化图例显示
                    if (option.legend) {
                        option.legend.formatter = function(name) {
                            // 变量名过长时截断显示
                            if (name && name.length > 15) {
                                return name.substring(0, 15) + '...';
                            }
                            return name;
                        };
                    }
                    
                    // 优化Y轴数字格式和变量名显示
                    const formatAxisLabel = (value) => {
                        // 格式化数字，去除多余小数位
                        if (Math.abs(value) >= 100) {
                            return value.toFixed(0);  // 大数值不需要小数位
                        } else if (Math.abs(value) >= 10) {
                            return value.toFixed(1);  // 保留1位小数
                        } else if (Math.abs(value) >= 1) {
                            return value.toFixed(2);  // 保留2位小数
                        } else {
                            return value.toFixed(3);  // 小数值最多保留3位小数
                        }
                    };
                    
                    // 处理单个Y轴的情况
                    if (option.yAxis && !Array.isArray(option.yAxis)) {
                        option.yAxis.axisLabel = {
                            formatter: formatAxisLabel,
                            color: '#fff'
                        };
                    }
                    
                    // 处理多个Y轴的情况
                    if (option.yAxis && Array.isArray(option.yAxis)) {
                        option.yAxis.forEach(axis => {
                            // 格式化坐标轴标签
                            axis.axisLabel = {
                                formatter: formatAxisLabel,
                                color: '#fff'
                            };
                            
                            // 优化变量名显示
                            if (axis.name && axis.name.length > 12) {
                                axis.name = axis.name.substring(0, 12) + '...';
                            }
                            
                            // 减小坐标轴名称与轴的间距
                            if (axis.nameGap === undefined) {
                                axis.nameGap = 10;
                            }
                            
                            // 调整offset，减少坐标轴间的距离
                            if (axis.position === 'right' && axis.offset !== undefined) {
                                axis.offset = Math.max(10, axis.offset * 0.7);
                            } else if (axis.position === 'left' && axis.offset !== undefined) {
                                axis.offset = Math.max(10, axis.offset * 0.7);
                            }
                        });
                    }
                    
                    // 优化数据缩放组件位置和样式
                    if (option.dataZoom && Array.isArray(option.dataZoom)) {
                        for (let i = 0; i < option.dataZoom.length; i++) {
                            if (option.dataZoom[i].type === 'slider') {
                                option.dataZoom[i].bottom = 10;
                                option.dataZoom[i].height = 25;
                            }
                        }
                    }
                }
                
                // 应用图表配置
                this.variableChart.setOption(option);
                console.log('ECharts 图表已渲染');
                
                // 添加窗口大小调整监听
                if (this.resizeChartHandler) {
                    window.removeEventListener('resize', this.resizeChartHandler);
                }
                
                this.resizeChartHandler = () => {
                    if (this.variableChart) {
                        this.variableChart.resize();
                    }
                };
                
                window.addEventListener('resize', this.resizeChartHandler);
            } catch (error) {
                console.error('渲染图表出错:', error);
            }
        },

        // 获取统计值
        getStatValue(type) {
            try {
                if (!this.selectedVariables || this.selectedVariables.length === 0) {
                    return '-';
                }
                
                // 获取第一个选中变量的数据
                const variableName = this.selectedVariables[0].name;
                
                if (this.variableData && this.variableData.length > 0) {
                    // 获取所有有效数值
                    const values = this.variableData
                        .filter(item => item[variableName] !== undefined && item[variableName] !== null)
                        .map(item => this.parseNumericValue(item[variableName]))
                        .filter(value => value !== null);
                        
                    if (values.length === 0) {
                        return '-';
                    }
                    
                    let result = 0;
                    switch (type) {
                        case 'max':
                            result = Math.max(...values);
                            break;
                        case 'min':
                            result = Math.min(...values);
                            break;
                        case 'avg':
                            result = values.reduce((a, b) => a + b, 0) / values.length;
                            break;
                        case 'std':
                            // 标准差计算
                            const avg = values.reduce((a, b) => a + b, 0) / values.length;
                            const squareDiffs = values.map(value => {
                                const diff = value - avg;
                                return diff * diff;
                            });
                            const avgSquareDiff = squareDiffs.reduce((a, b) => a + b, 0) / squareDiffs.length;
                            result = Math.sqrt(avgSquareDiff);
                            break;
                        default:
                            return '-';
                    }
                    
                    // 检查变量名是否包含功率相关字段
                    const isPowerVariable = 
                        variableName.includes('power') || 
                        variableName.includes('_power_') || 
                        variableName.includes('_power.') ||
                        variableName.includes('_power');
                    
                    // 根据变量类型和数值大小决定小数位数
                    if (isPowerVariable) {
                        // 功率变量保留1位小数
                        return result.toFixed(1);
                    } else {
                        // 其他变量保留合适的小数位数
                        if (Math.abs(result) >= 100) {
                            return result.toFixed(1);
                        } else if (Math.abs(result) >= 10) {
                            return result.toFixed(2);
                        } else {
                            return result.toFixed(3);
                        }
                    }
                }
                
                return '-';
            } catch (error) {
                console.error('计算统计值出错:', error);
                return '-';
            }
        },

        // ===== 报表分析页面方法 =====

        // 清除报表变量选择
        clearReportVariables() {
            this.selectedReportVariables = [];
            this.reportData = [];
        },

        // 加载报表数据
        loadReportData() {
            if (!this.socket) {
                console.error('WebSocket未连接');
                this.showReportError('WebSocket未连接，请刷新页面重试');
                return;
            }
            
            if (!this.selectedReportVariables || this.selectedReportVariables.length === 0) {
                console.warn('请选择至少一个变量');
                this.showReportError('请至少选择一个变量');
                return;
            }

            // 检查变量数量限制
            const maxVariables = 20;
            if (this.selectedReportVariables.length > maxVariables) {
                console.warn(`变量数量超过限制: ${this.selectedReportVariables.length} > ${maxVariables}`);
                this.showReportError(`变量数量不能超过 ${maxVariables} 个，您已选择 ${this.selectedReportVariables.length} 个`);
                return;
            }

            this.reportLoading = true;
            this.reportData = []; // 清除旧数据

            // 准备时间范围
            let startTime = null;
            let endTime = null;

            if (this.reportTimeRange === 'custom') {
                startTime = this.reportStartTime ? Math.floor(new Date(this.reportStartTime).getTime() / 1000) : null;
                endTime = this.reportEndTime ? Math.floor(new Date(this.reportEndTime).getTime() / 1000) : Math.floor(Date.now() / 1000);
            } else {
                // 预设时间范围
                const now = Math.floor(Date.now() / 1000);
                endTime = now;

                switch (this.reportTimeRange) {
                    case '5m': startTime = now - 5 * 60; break;
                    case '15m': startTime = now - 15 * 60; break;
                    case '30m': startTime = now - 30 * 60; break;
                    case '1h': startTime = now - 60 * 60; break;
                    case '6h': startTime = now - 6 * 60 * 60; break;
                    case '12h': startTime = now - 12 * 60 * 60; break;
                    case '24h': startTime = now - 24 * 60 * 60; break;
                    default: startTime = now - 60 * 60; // 默认1小时
                }
            }

            // 显示表格区域加载中提示
            const tableContainer = document.querySelector('.report-analysis-content .table-container');
            if (tableContainer) {
                // 清除内容
                while (tableContainer.firstChild) {
                    tableContainer.removeChild(tableContainer.firstChild);
                }
                
                // 添加加载中提示
                const msg = document.createElement('div');
                msg.className = 'loading-message-center';
                msg.textContent = '正在加载数据...';
                tableContainer.appendChild(msg);
            }

            // 准备请求数据
            const variableNames = this.selectedReportVariables.map(v => v.name);
            
            const requestData = {
                variable_names: variableNames,
                start_time: startTime,
                end_time: endTime
            };

            console.log('发送报表数据请求:', requestData);
            console.log(`请求 ${variableNames.length} 个变量的数据`);
            
            // 注册接收事件处理器
            this.socket.off('variable_report_data_result'); // 先移除以前的处理器
            this.socket.on('variable_report_data_result', (rawData) => {
                this.handleReportData(rawData);
            });
            
            // 设置请求超时
            if (this.reportTimeout) {
                clearTimeout(this.reportTimeout);
            }
            
            this.reportTimeout = setTimeout(() => {
                if (this.reportLoading) {
                    this.reportLoading = false;
                    console.error('报表数据请求超时');
                    this.showReportError('请求超时，请减少变量数量或缩小时间范围后重试');
                }
            }, 60000); // 60秒超时
            
            // 发送请求到服务器
            this.socket.emit('get_variable_report_data', JSON.stringify(requestData));
        },

        // 显示报表错误消息
        showReportError(message) {
            this.reportLoading = false;
            
            // 显示错误信息
            const tableContainer = document.querySelector('.report-analysis-content .table-container');
            if (tableContainer) {
                while (tableContainer.firstChild) {
                    tableContainer.removeChild(tableContainer.firstChild);
                }
                const msg = document.createElement('div');
                msg.className = 'error-message-center';
                msg.textContent = message;
                tableContainer.appendChild(msg);
            }
        },

        // 处理报表数据响应
        handleReportData(rawData) {
            try {
                console.log('处理报表数据响应');
                this.reportLoading = false;
                
                // 清除超时计时器
                if (this.reportTimeout) {
                    clearTimeout(this.reportTimeout);
                    this.reportTimeout = null;
                }
                
                const response = typeof rawData === 'string' ? JSON.parse(rawData) : rawData;
                
                if (response.error) {
                    console.error('获取报表数据出错:', response.error);
                    this.showReportError(response.error);
                    return;
                }
                
                // 更新报表数据
                if (response.data && response.data.length > 0) {
                    this.reportData = response.data;
                    console.log(`收到 ${this.reportData.length} 条报表数据`);
                    
                    // 渲染报表表格
                    this.renderReportTable();
                } else {
                    console.warn('响应中没有报表数据');
                    this.showReportError('所选时间范围内无数据');
                }
            } catch (error) {
                console.error('处理报表数据响应时出错:', error);
                this.reportLoading = false;
                this.showReportError(`处理数据出错: ${error.message}`);
            }
        },

        // 渲染报表表格
        renderReportTable() {
            if (!this.reportData || this.reportData.length === 0) {
                console.warn('没有报表数据可渲染');
                this.showReportError('没有可用数据');
                return;
            }
            
            console.log(`开始渲染报表表格，${this.reportData.length}条数据`);
            const startTime = performance.now();
            
            // 获取表格容器
            const tableContainer = document.querySelector('.report-analysis-content .table-container');
            if (!tableContainer) {
                console.error('未找到报表表格容器');
                return;
            }
            
            // 清空容器
            while (tableContainer.firstChild) {
                tableContainer.removeChild(tableContainer.firstChild);
            }
            
            // 创建表格和头部
            const table = document.createElement('table');
            table.className = 'report-table';
            
            // 创建表头
            const thead = document.createElement('thead');
            const headerRow = document.createElement('tr');
            
            // 添加时间戳列
            const timeHeader = document.createElement('th');
            timeHeader.textContent = '时间戳';
            headerRow.appendChild(timeHeader);
            
            // 添加变量列
            this.selectedReportVariables.forEach(variable => {
                const th = document.createElement('th');
                th.textContent = variable.label;
                headerRow.appendChild(th);
            });
            
            thead.appendChild(headerRow);
            table.appendChild(thead);
            
            // 创建表格内容
            const tbody = document.createElement('tbody');
            
            // 确定是否需要分批渲染
            const batchSize = 100; // 每批处理的行数
            const totalRows = this.reportData.length;
            
            if (totalRows > 1000) {
                console.log(`数据量大(${totalRows}行)，使用分批渲染`);
                
                // 显示加载进度指示器
                const loadingInfo = document.createElement('div');
                loadingInfo.className = 'table-loading-info';
                loadingInfo.textContent = '大量数据，正在分批渲染...';
                loadingInfo.style.position = 'sticky';
                loadingInfo.style.top = '0';
                loadingInfo.style.background = 'rgba(16, 33, 49, 0.9)';
                loadingInfo.style.padding = '8px';
                loadingInfo.style.textAlign = 'center';
                loadingInfo.style.zIndex = '100';
                loadingInfo.style.color = '#00aeff';
                tableContainer.appendChild(loadingInfo);
                
                // 先添加表格
                tableContainer.appendChild(table);
                table.appendChild(tbody);
                
                // 使用requestAnimationFrame逐批渲染
                let processedRows = 0;
                
                const renderBatch = (startIndex) => {
                    const fragment = document.createDocumentFragment();
                    const endIndex = Math.min(startIndex + batchSize, totalRows);
                    
                    for (let i = startIndex; i < endIndex; i++) {
                        const rowData = this.reportData[i];
                        const row = this.createTableRow(rowData);
                        fragment.appendChild(row);
                        processedRows++;
                    }
                    
                    tbody.appendChild(fragment);
                    loadingInfo.textContent = `正在渲染... (${Math.floor(processedRows/totalRows*100)}%)`;
                    
                    if (endIndex < totalRows) {
                        // 继续渲染下一批
                        requestAnimationFrame(() => renderBatch(endIndex));
                    } else {
                        // 渲染完成，移除加载信息
                        tableContainer.removeChild(loadingInfo);
                        console.log(`报表渲染完成，耗时: ${(performance.now() - startTime).toFixed(0)}ms`);
                    }
                };
                
                // 开始渲染第一批
                requestAnimationFrame(() => renderBatch(0));
            } else {
                // 数据量不大，一次性渲染
                this.reportData.forEach(rowData => {
                    const row = this.createTableRow(rowData);
                    tbody.appendChild(row);
                });
                
                // 添加表格到容器
                table.appendChild(tbody);
                tableContainer.appendChild(table);
                console.log(`报表渲染完成，耗时: ${(performance.now() - startTime).toFixed(0)}ms`);
            }
        },

        // 创建表格行
        createTableRow(rowData) {
            const row = document.createElement('tr');
            
            // 添加时间戳单元格
            const timeCell = document.createElement('td');
            timeCell.textContent = this.formatTimestamp(rowData.timestamp);
            row.appendChild(timeCell);
            
            // 添加变量值单元格
            this.selectedReportVariables.forEach(variable => {
                const td = document.createElement('td');
                
                // 获取变量值
                const value = rowData[variable.name];
                
                // 格式化值
                td.textContent = this.formatCellValue(value, variable.name);
                
                row.appendChild(td);
            });
            
            return row;
        },

        // 格式化单元格值
        formatCellValue(value, variableName) {
            if (value === null || value === undefined) {
                return '-';
            }
            
            // 特殊处理电解槽状态
            if (variableName.includes('electrolyzer_status')) {
                return value; // 不进行格式化
            }
            
            // 功率相关变量只保留1位小数
            const powerVariables = [
                'grid_power', 'grid_export_power', 'grid_import_power', 'solar_power', 
                'wind_power', 'storage_power', 'hydrogen_real_power', 'hydrogen_set_power',
                'follow_storage', 'grid_storage', 'hydrogen_total_power',
                'electrolyzer_set_power', 'electrolyzer_real_power'
            ];
            
            // 检查变量名是否包含功率相关字段
            const isPowerVariable = 
                powerVariables.includes(variableName) || 
                variableName.includes('_power_') || 
                variableName.includes('_set_power') || 
                variableName.includes('_real_power');
            
            // 格式化数值，如果是数值的话
            if (typeof value === 'number' || !isNaN(parseFloat(value))) {
                const numValue = parseFloat(value);
                if (isPowerVariable) {
                    return numValue.toFixed(1); // 功率变量保留1位小数
                } else {
                    // 其他变量保留最多3位小数
                    // 根据数字大小动态调整小数位
                    if (Math.abs(numValue) >= 100) {
                        return numValue.toFixed(1);
                    } else if (Math.abs(numValue) >= 10) {
                        return numValue.toFixed(2);
                    } else {
                        return numValue.toFixed(3);
                    }
                }
            }
            
            return value;
        },

        // 格式化时间戳
        formatTimestamp(timestamp) {
            if (!timestamp) {
                return '-';
            }
            
            const date = new Date(timestamp * 1000);
            
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const hour = String(date.getHours()).padStart(2, '0');
            const minute = String(date.getMinutes()).padStart(2, '0');
            const second = String(date.getSeconds()).padStart(2, '0');
            
            return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
        },

        // 连接WebSocket服务器
        connectWebSocket() {
            try {
                // 获取WebSocket服务器地址
                const wsUrl = CONFIG.WS_URL;
                
                // 创建Socket.io连接，增加重试次数和超时设置
                this.socket = io(wsUrl, {
                    reconnectionAttempts: 10,  // 增加重连尝试次数
                    reconnectionDelay: 2000,   // 重连间隔2秒
                    timeout: 10000,            // 连接超时时间10秒
                    transports: ['websocket', 'polling'],  // 允许WebSocket和polling传输
                    autoConnect: true,         // 自动连接
                    upgrade: true              // 允许传输升级
                });
                
                // 连接事件
                this.socket.on('connect', () => {
                    console.log('WebSocket连接成功');
                    this.socketConnected = true;
                    this.systemStatus = '已连接';
                    // 请求历史数据
                    this.socket.emit('get_history');
                    // 请求变量列表
                    this.socket.emit('get_variable_list');
                });
                
                // 断开连接事件
                this.socket.on('disconnect', (reason) => {
                    console.log('WebSocket断开连接，原因:', reason);
                    this.socketConnected = false;
                    this.systemStatus = '连接断开';
                    // 尝试重新连接
                    setTimeout(() => this.connectWebSocket(), 5000);
                });
                
                // 连接错误事件
                this.socket.on('connect_error', (error) => {
                    console.error('WebSocket连接错误:', error);
                    this.socketConnected = false;
                    this.systemStatus = '连接错误';
                    // 尝试重新连接
                    setTimeout(() => this.connectWebSocket(), 5000);
                });
                
                // 实时数据事件
                this.socket.on('realtime_data', (dataString) => {
                    try {
                        const data = JSON.parse(dataString);
                        handleNewData(data);
                    } catch (error) {
                        console.error('解析实时数据失败:', error);
                    }
                });
                
                // 历史数据事件
                this.socket.on('history_data', (dataString) => {
                    try {
                        const dataArray = JSON.parse(dataString);
                        handleHistoryData(dataArray);
                    } catch (error) {
                        console.error('解析历史数据失败:', error);
                    }
                });
                
                // 变量列表事件
                this.socket.on('variable_list', (dataString) => {
                    try {
                        const variableList = JSON.parse(dataString);
                        console.log('收到变量列表:', variableList);
                        this.variables = variableList;
                    } catch (error) {
                        console.error('解析变量列表失败:', error);
                    }
                });
                
                // 变量数据响应处理
                this.socket.on('variable_data_result', (dataString) => {
                    try {
                        const response = JSON.parse(dataString);
                        this.dataLoading = false;
                        console.log('收到变量数据响应:', response);
                        
                        if (response.error) {
                            console.error('获取变量数据出错:', response.error);
                            // 显示错误消息
                            const chartContainer = document.getElementById('variable-chart-container');
                            if (chartContainer && this.variableChart) {
                                this.variableChart.dispose();
                                this.variableChart = null;
                                
                                // 显示错误提示
                                chartContainer.innerHTML = `<div class="error-message" style="color:#ff6b6b;padding:20px;text-align:center;">
                                    <i class="fas fa-exclamation-circle"></i> 加载数据时出错: ${response.error}
                                </div>`;
                            }
                            return;
                        }
                        
                        // 更新变量数据
                        if (response.data) {
                            this.variableData = response.data;
                            
                            // 检查是否没有任何有效数据
                            let hasValidData = false;
                            const selectedVarNames = this.selectedVariables.map(v => v.name);
                            
                            for (const item of response.data) {
                                for (const varName of selectedVarNames) {
                                    if (item[varName] !== undefined && item[varName] !== null) {
                                        hasValidData = true;
                                        break;
                                    }
                                }
                                if (hasValidData) break;
                            }
                            
                            if (!hasValidData && selectedVarNames.length > 0) {
                                console.warn('所选变量没有有效数据');
                                const chartContainer = document.getElementById('variable-chart-container');
                                if (chartContainer) {
                                    if (this.variableChart) {
                                        this.variableChart.dispose();
                                        this.variableChart = null;
                                    }
                                    // 显示无数据提示
                                    chartContainer.innerHTML = `<div class="no-data-message" style="color:#83a7c9;padding:20px;text-align:center;">
                                        <i class="fas fa-info-circle"></i> 所选变量在当前时间范围内没有数据
                                    </div>`;
                                }
                                return;
                            }
                        }
                        
                        // 渲染图表
                        if (response.chart) {
                            console.log('收到图表配置:', response.chart);
                            
                            // 在下一个事件循环中渲染图表，确保DOM已更新
                            this.$nextTick(() => {
                                try {
                                    this.renderEChart(response.chart);
                                    console.log('图表已渲染');
                                } catch (renderError) {
                                    console.error('渲染图表时出错:', renderError);
                                    // 显示渲染错误
                                    const chartContainer = document.getElementById('variable-chart-container');
                                    if (chartContainer) {
                                        chartContainer.innerHTML = `<div class="error-message" style="color:#ff6b6b;padding:20px;text-align:center;">
                                            <i class="fas fa-exclamation-circle"></i> 渲染图表时出错: ${renderError.message}
                                        </div>`;
                                    }
                                }
                            });
                        } else {
                            console.warn('响应中没有图表配置或所有变量均无数据');
                            // 清除图表
                            if (this.variableChart) {
                                this.variableChart.clear();
                            }
                        }
                    } catch (error) {
                        console.error('解析变量数据响应失败:', error);
                        this.dataLoading = false;
                        
                        // 显示错误提示
                        const chartContainer = document.getElementById('variable-chart-container');
                        if (chartContainer) {
                            chartContainer.innerHTML = `<div class="error-message" style="color:#ff6b6b;padding:20px;text-align:center;">
                                <i class="fas fa-exclamation-circle"></i> 解析数据时出错: ${error.message}
                            </div>`;
                        }
                    }
                });
                
                // 变量数据错误处理
                this.socket.on('variable_data_error', (errorString) => {
                    try {
                        const errorResponse = JSON.parse(errorString);
                        console.error('获取变量数据出错:', errorResponse.error);
                        this.dataLoading = false;
                    } catch (error) {
                        console.error('解析错误信息失败:', error);
                        this.dataLoading = false;
                    }
                });
                
                // 报表数据响应处理
                this.socket.on('variable_report_data_result', (dataString) => {
                    console.log('收到报表数据响应');
                    this.handleReportData(dataString);
                });
                
                // 发送自定义的连接消息
                setTimeout(() => {
                    this.socket.emit('get_history');
                    console.log('已请求历史数据');
                }, 1000);
                
                // 填充变量列表
                setTimeout(() => {
                    this.populateVariables();
                }, 1000);
                
            } catch (error) {
                console.error('初始化WebSocket时出错:', error);
                this.systemStatus = '连接错误';
            }
        },

        // 格式化日期时间为输入框格式
        formatDatetimeForInput(date) {
            const pad = (num) => num.toString().padStart(2, '0');
            const year = date.getFullYear();
            const month = pad(date.getMonth() + 1);
            const day = pad(date.getDate());
            const hours = pad(date.getHours());
            const minutes = pad(date.getMinutes());
            
            return `${year}-${month}-${day}T${hours}:${minutes}`;
        },

        // 导出报表数据为CSV
        exportReportData() {
            if (!this.reportData || this.reportData.length === 0) {
                console.warn('没有可导出的数据');
                return;
            }
            
            // 准备CSV内容
            let csvContent = 'data:text/csv;charset=utf-8,';
            
            // 添加表头
            let headers = ['时间戳'];
            this.selectedReportVariables.forEach(variable => {
                headers.push(variable.label);
            });
            csvContent += headers.join(',') + '\r\n';
            
            // 添加数据行
            this.reportData.forEach(rowData => {
                let row = [this.formatTimestamp(rowData.timestamp)];
                this.selectedReportVariables.forEach(variable => {
                    const value = rowData[variable.name];
                    if (value !== null && value !== undefined) {
                        row.push(this.formatCellValue(value, variable.name));
                    } else {
                        row.push('');
                    }
                });
                csvContent += row.join(',') + '\r\n';
            });
            
            // 创建下载链接
            const encodedUri = encodeURI(csvContent);
            const link = document.createElement('a');
            link.setAttribute('href', encodedUri);
            link.setAttribute('download', `报表数据_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`);
            document.body.appendChild(link);
            
            // 触发下载
            link.click();
            
            // 清理
            document.body.removeChild(link);
        },

        // 切换主题

        // Matrix数字雨效果初始化
        initMatrixRain() {
            const canvas = document.getElementById('matrix-canvas');
            if (!canvas) return;

            const ctx = canvas.getContext('2d');
            
            // 设置canvas尺寸
            const resizeCanvas = () => {
                canvas.width = window.innerWidth;
                canvas.height = window.innerHeight;
            };
            resizeCanvas();
            window.addEventListener('resize', resizeCanvas);

            // 字符集 - 大部分数字+一些字母
            const chars = '01234567890123456789012345678901234567890123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
            const charArray = chars.split('');

            // 字体大小
            const fontSize = 24;
            const columns = canvas.width / fontSize;

            // 每列的当前位置
            const drops = [];
            for (let i = 0; i < columns; i++) {
                drops[i] = Math.random() * -100;
            }

            // 绘制函数
            const draw = () => {
                // 半透明黑色背景，产生拖尾效果
                ctx.fillStyle = 'rgba(0, 0, 0, 0.05)';
                ctx.fillRect(0, 0, canvas.width, canvas.height);

                // 设置字体
                ctx.font = fontSize + 'px monospace';

                // 绘制字符
                for (let i = 0; i < drops.length; i++) {
                    // 随机字符
                    const char = charArray[Math.floor(Math.random() * charArray.length)];
                    
                    // 渐变颜色效果
                    const opacity = 1 - (drops[i] * fontSize) / canvas.height;
                    ctx.fillStyle = `rgba(0, 255, 140, 1.0)`;
                    
                    // 绘制字符
                    ctx.fillText(char, i * fontSize, drops[i] * fontSize);

                    // 重置已经到达底部的字符
                    if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
                        drops[i] = 0;
                    }

                    // 移动字符
                    drops[i]++;
                }
            };

            // 动画循环
            this.matrixInterval = setInterval(draw, 35);
            this.matrixResizeHandler = resizeCanvas;
        },

        // 销毁Matrix效果
        destroyMatrixRain() {
            if (this.matrixInterval) {
                clearInterval(this.matrixInterval);
                this.matrixInterval = null;
            }
            if (this.matrixResizeHandler) {
                window.removeEventListener('resize', this.matrixResizeHandler);
                this.matrixResizeHandler = null;
            }
        },
    },
    created() {
        // 初始化暗色主题
        document.documentElement.setAttribute('data-theme', 'dark');
        document.body.classList.remove('light-theme');
        
        // 初始化数据 
        this.latestData = APP_DATA.latestData;
        
        // 设置默认时间
        const now = new Date();
        this.startTime = this.formatDatetimeForInput(new Date(now.getTime() - 60 * 60 * 1000)); // 默认1小时前
        this.endTime = this.formatDatetimeForInput(now);
        
        // 设置报表自定义时间范围默认值
        this.reportStartTime = this.formatDatetimeForInput(new Date(now.getTime() - 60 * 60 * 1000)); // 默认1小时前
        this.reportEndTime = this.formatDatetimeForInput(now);
        
        // 开始时间更新
        this.updateTime();
        
        // 连接WebSocket
        this.connectWebSocket();
        
        // 注册事件处理器
        if (this.socket) {
            // 监听报表数据响应
            this.socket.on('variable_report_data_result', (rawData) => {
                const speed = this.speed; // 获取当前速度
                const data = JSON.parse(rawData);
                data.forEach(item => {
                    item.timestamp *= speed; // 按速度倍数调整时间戳
                });
                this.handleReportData(JSON.stringify(data));
            });
        }
    },
    mounted() {
        // 初始化时间
        this.updateTime();
        
        // 启动时间更新定时器，每秒更新一次
        this.timeUpdateInterval = setInterval(() => {
            this.updateTime();
        }, 1000);
        
        // 添加仿真信息显示区域
        addSimulationInfoToDOM();
        
        // 初始化WebSocket连接
        initWebSocket();
        
        // 如果当前是首页，初始化Matrix雨效果
        if (this.currentPage === 1) {
            // 延迟初始化，确保canvas元素已加载
            setTimeout(() => {
                this.initMatrixRain();
            }, 200);
        }
    },
    
    beforeDestroy() {
        // 清理定时器
        if (this.timeUpdateInterval) {
            clearInterval(this.timeUpdateInterval);
        }
        
        // 清理页面更新定时器
        if (this.pageUpdateInterval) {
            clearInterval(this.pageUpdateInterval);
        }
        
        // 清理矩阵雨
        this.destroyMatrixRain();
        
        // 清理图表
        if (this.variableChart) {
            this.variableChart.dispose();
        }
    }
});

// 主函数
function main() {
    console.log('主函数执行');
    // 添加仿真信息显示区域
    addSimulationInfoToDOM();
}

// 在页面加载完成后调用main函数
document.addEventListener('DOMContentLoaded', main);

/**
 * 添加仿真信息显示区域到DOM
 */
function addSimulationInfoToDOM() {
    // 检查是否已经存在
    if (document.getElementById('simulation-info')) {
        return;
    }
    
    // 创建仿真信息显示区域
    const simInfoDiv = document.createElement('div');
    simInfoDiv.id = 'simulation-info';
    simInfoDiv.style.position = 'fixed';
    simInfoDiv.style.top = '10px';
    simInfoDiv.style.right = '10px';
    simInfoDiv.style.backgroundColor = 'rgba(0, 0, 0, 0.7)';
    simInfoDiv.style.color = '#00ff00';
    simInfoDiv.style.padding = '10px';
    simInfoDiv.style.borderRadius = '5px';
    simInfoDiv.style.zIndex = '9999';
    simInfoDiv.style.display = 'none';
    simInfoDiv.style.fontFamily = 'monospace';
    simInfoDiv.style.fontSize = '14px';
    
    // 添加仿真速度和时间信息
    const speedDiv = document.createElement('div');
    speedDiv.id = 'simulation-speed';
    speedDiv.textContent = '仿真速度: 1倍';
    
    const timeDiv = document.createElement('div');
    timeDiv.id = 'simulation-time';
    timeDiv.textContent = '仿真时间: -';
    
    simInfoDiv.appendChild(speedDiv);
    simInfoDiv.appendChild(timeDiv);
    
    // 添加到文档
    document.body.appendChild(simInfoDiv);
}

// 初始化WebSocket连接
function initWebSocket() {
    try {
        if (CONFIG.DEBUG) {
            console.log('正在初始化WebSocket连接...');
            console.log('主WebSocket地址:', CONFIG.WS_URL);
            console.log('备用WebSocket地址:', CONFIG.BACKUP_WS_URLS);
        }

        // 创建WebSocket连接
        APP_DATA.socket = io(CONFIG.WS_URL, {
            reconnectionAttempts: 10,  // 增加重连尝试次数
            reconnectionDelay: 2000,   // 重连间隔2秒
            timeout: 10000,            // 连接超时时间10秒
            transports: ['websocket', 'polling'],  // 允许WebSocket和polling传输
            autoConnect: true,         // 自动连接
            upgrade: true              // 允许传输升级
        });

        // 连接成功处理
        APP_DATA.socket.on('connect', () => {
            console.log('WebSocket连接成功');
            document.getElementById('app').classList.add('connected');
            APP_DATA.connected = true;
            APP_DATA.systemStatus = '已连接';
            app.systemStatus = APP_DATA.systemStatus;

            // 请求历史数据
            APP_DATA.socket.emit('get_history');

            // 如果是模拟模式，启用模拟数据处理
            if (CONFIG.DEBUG) {
                console.log('WebSocket连接ID:', APP_DATA.socket.id);
                console.log('WebSocket传输方式:', APP_DATA.socket.io.engine.transport.name);
            }
        });

        // 连接断开处理
        APP_DATA.socket.on('disconnect', (reason) => {
            console.log('WebSocket连接断开，原因:', reason);
            document.getElementById('app').classList.remove('connected');
            APP_DATA.connected = false;
            APP_DATA.systemStatus = '连接断开';
            app.systemStatus = APP_DATA.systemStatus;

            // 如果是因为传输错误断开，尝试使用备用地址重连
            if (reason === 'transport error' || reason === 'transport close') {
                tryBackupConnections();
            }
        });

        // 连接错误处理
        APP_DATA.socket.on('connect_error', (error) => {
            console.error('WebSocket连接错误:', error);
            document.getElementById('app').classList.remove('connected');
            APP_DATA.connected = false;
            APP_DATA.systemStatus = '连接失败';
            app.systemStatus = APP_DATA.systemStatus;

            // 尝试使用备用地址
            tryBackupConnections();
        });

        // 实时数据处理
        APP_DATA.socket.on('realtime_data', (data) => {
            try {
                const parsedData = JSON.parse(data);
                if (CONFIG.DEBUG) {
                    console.log('收到实时数据:', parsedData.timestamp);
                }
                handleNewData(parsedData);
            } catch (e) {
                console.error('解析实时数据时出错:', e);
                console.error('原始数据:', data);
            }
        });

        // 历史数据处理
        APP_DATA.socket.on('history_data', (data) => {
            try {
                const parsedData = JSON.parse(data);
                if (CONFIG.DEBUG) {
                    console.log('收到历史数据, 条数:', Array.isArray(parsedData) ? parsedData.length : 0);
                }
                handleHistoryData(parsedData);
            } catch (e) {
                console.error('解析历史数据时出错:', e);
                console.error('原始数据:', data);
            }
        });

        // 变量列表处理
        APP_DATA.socket.on('variable_list', (data) => {
            try {
                const parsedData = JSON.parse(data);
                if (CONFIG.DEBUG) {
                    console.log('收到变量列表, 条数:', Array.isArray(parsedData) ? parsedData.length : 0);
                }
                app.variables = parsedData;
            } catch (e) {
                console.error('解析变量列表时出错:', e);
                console.error('原始数据:', data);
            }
        });

        // 变量数据处理
        APP_DATA.socket.on('variable_data_result', (dataString) => {
            try {
                const response = JSON.parse(dataString);
                this.dataLoading = false;
                console.log('收到变量数据响应:', response);
                
                if (response.error) {
                    console.error('获取变量数据出错:', response.error);
                    // 显示错误消息
                    const chartContainer = document.getElementById('variable-chart-container');
                    if (chartContainer && this.variableChart) {
                        this.variableChart.dispose();
                        this.variableChart = null;
                        
                        // 显示错误提示
                        chartContainer.innerHTML = `<div class="error-message" style="color:#ff6b6b;padding:20px;text-align:center;">
                            <i class="fas fa-exclamation-circle"></i> 加载数据时出错: ${response.error}
                        </div>`;
                    }
                    return;
                }
                
                // 更新变量数据
                if (response.data) {
                    this.variableData = response.data;
                    
                    // 检查是否没有任何有效数据
                    let hasValidData = false;
                    const selectedVarNames = this.selectedVariables.map(v => v.name);
                    
                    for (const item of response.data) {
                        for (const varName of selectedVarNames) {
                            if (item[varName] !== undefined && item[varName] !== null) {
                                hasValidData = true;
                                break;
                            }
                        }
                        if (hasValidData) break;
                    }
                    
                    if (!hasValidData && selectedVarNames.length > 0) {
                        console.warn('所选变量没有有效数据');
                        const chartContainer = document.getElementById('variable-chart-container');
                        if (chartContainer) {
                            if (this.variableChart) {
                                this.variableChart.dispose();
                                this.variableChart = null;
                            }
                            // 显示无数据提示
                            chartContainer.innerHTML = `<div class="no-data-message" style="color:#83a7c9;padding:20px;text-align:center;">
                                <i class="fas fa-info-circle"></i> 所选变量在当前时间范围内没有数据
                            </div>`;
                        }
                        return;
                    }
                }
                
                // 渲染图表
                if (response.chart) {
                    console.log('收到图表配置:', response.chart);
                    
                    // 在下一个事件循环中渲染图表，确保DOM已更新
                    this.$nextTick(() => {
                        try {
                            this.renderEChart(response.chart);
                            console.log('图表已渲染');
                        } catch (renderError) {
                            console.error('渲染图表时出错:', renderError);
                            // 显示渲染错误
                            const chartContainer = document.getElementById('variable-chart-container');
                            if (chartContainer) {
                                chartContainer.innerHTML = `<div class="error-message" style="color:#ff6b6b;padding:20px;text-align:center;">
                                    <i class="fas fa-exclamation-circle"></i> 渲染图表时出错: ${renderError.message}
                                </div>`;
                            }
                        }
                    });
                } else {
                    console.warn('响应中没有图表配置或所有变量均无数据');
                    // 清除图表
                    if (this.variableChart) {
                        this.variableChart.clear();
                    }
                }
            } catch (error) {
                console.error('解析变量数据响应失败:', error);
                this.dataLoading = false;
                
                // 显示错误提示
                const chartContainer = document.getElementById('variable-chart-container');
                if (chartContainer) {
                    chartContainer.innerHTML = `<div class="error-message" style="color:#ff6b6b;padding:20px;text-align:center;">
                        <i class="fas fa-exclamation-circle"></i> 解析数据时出错: ${error.message}
                    </div>`;
                }
            }
        });
        
        // 报表数据处理
        APP_DATA.socket.on('variable_report_data_result', (dataString) => {
            console.log('收到报表数据响应');
            this.handleReportData(dataString);
        });

    } catch (error) {
        console.error('初始化WebSocket时出错:', error);
        APP_DATA.systemStatus = '连接错误';
        app.systemStatus = APP_DATA.systemStatus;

        // 尝试使用备用地址
        tryBackupConnections();
    }
}

/**
 * 尝试使用备用WebSocket地址连接
 */
function tryBackupConnections() {
    if (!CONFIG.BACKUP_WS_URLS || CONFIG.BACKUP_WS_URLS.length === 0) {
        console.log('没有可用的备用WebSocket地址');
        return;
    }

    // 如果当前已经有连接，先关闭
    if (APP_DATA.socket) {
        APP_DATA.socket.close();
    }

    console.log('尝试使用备用WebSocket地址连接...');

    // 尝试每个备用地址
    for (let i = 0; i < CONFIG.BACKUP_WS_URLS.length; i++) {
        const backupUrl = CONFIG.BACKUP_WS_URLS[i];
        if (backupUrl === CONFIG.WS_URL) continue; // 跳过主地址

        console.log(`尝试备用地址 ${i+1}/${CONFIG.BACKUP_WS_URLS.length}: ${backupUrl}`);

        try {
            APP_DATA.socket = io(backupUrl, {
                reconnectionAttempts: 5,
                reconnectionDelay: 2000,
                timeout: 8000,
                transports: ['websocket', 'polling'],
                autoConnect: true,
                upgrade: true
            });

            // 设置连接事件处理
            APP_DATA.socket.on('connect', () => {
                console.log(`使用备用地址 ${backupUrl} 连接成功`);
                document.getElementById('app').classList.add('connected');
                APP_DATA.connected = true;
                APP_DATA.systemStatus = '已连接(备用)';
                app.systemStatus = APP_DATA.systemStatus;

                // 请求历史数据
                APP_DATA.socket.emit('get_history');
            });

            // 设置其他事件处理
            APP_DATA.socket.on('disconnect', (reason) => {
                console.log(`备用地址 ${backupUrl} 连接断开，原因:`, reason);
                document.getElementById('app').classList.remove('connected');
                APP_DATA.connected = false;
                APP_DATA.systemStatus = '连接断开';
                app.systemStatus = APP_DATA.systemStatus;
            });

            APP_DATA.socket.on('connect_error', (error) => {
                console.error(`备用地址 ${backupUrl} 连接错误:`, error);
                // 这里不能使用continue，因为我们在回调函数中
                // 我们将在外部循环中处理下一个地址
            });

            // 设置数据处理事件
            APP_DATA.socket.on('realtime_data', (data) => {
                try {
                    const parsedData = JSON.parse(data);
                    handleNewData(parsedData);
                } catch (e) {
                    console.error('解析实时数据时出错:', e);
                }
            });

            APP_DATA.socket.on('history_data', (data) => {
                try {
                    const parsedData = JSON.parse(data);
                    handleHistoryData(parsedData);
                } catch (e) {
                    console.error('解析历史数据时出错:', e);
                }
            });

            // 如果成功创建了连接对象，就不再尝试其他备用地址
            break;

        } catch (error) {
            console.error(`尝试备用地址 ${backupUrl} 时出错:`, error);
        }
    }
}

/**
 * 处理新接收的数据
 * @param {Object} data - 新接收的数据
 */
function handleNewData(data) {
    // 初始化数据对象
    if (!data.data) data.data = {};

    // 处理聚合信息
    if (data.aggregation_info) {
        app.aggregationInfo = data.aggregation_info;
    } else {
        // 如果没有聚合信息，则重置为默认值
        app.aggregationInfo = { minutes: 1, count: 0 };
    }
    
    // 处理仿真速度信息
    const isSpeedMode = data.speed && data.speed > 1;
    
    // 只在调试模式下输出调试信息
    if (CONFIG.DEBUG && !isSpeedMode) {
        console.log('接收到的数据包含speed:', data.speed);
    }
    
    if (isSpeedMode) {
        // Speed模式处理
        if (app.simulationSpeed !== data.speed) {
            if (CONFIG.DEBUG) {
                console.log('设置仿真速度为:', data.speed);
                console.log(`Speed模式: ${data.speed}倍数据接收频率，时间戳保持真实时间`);
            }
        }
        app.simulationSpeed = data.speed;
        window.simulationSpeed = data.speed;
        
        // 显示仿真信息
        const infoEl = document.getElementById('simulation-info');
        if (infoEl) {
            infoEl.style.display = 'block';
            const speedDisplay = infoEl.querySelector('.speed-display');
            if (speedDisplay) {
                speedDisplay.textContent = `${data.speed}x`;
            }
        }
    } else {
        // 正常模式处理
        app.simulationSpeed = 1;
        window.simulationSpeed = 1;
        
        // 隐藏仿真信息显示区域
        const infoEl = document.getElementById('simulation-info');
        if (infoEl) {
            infoEl.style.display = 'none';
        }
    }

    // 根据模拟模式处理数据
    if (APP_DATA.useSimulation) {
        // 使用模拟数据时的处理
        // 系统状态变量
        if (!data.data.grid_connected_status) data.data.grid_connected_status = true;
        if (!data.data.storage_running_status) data.data.storage_running_status = true;
        if (!data.data.solar_power) data.data.solar_power = 2500;
        if (!data.data.system_enable_status) data.data.system_enable_status = true;
        if (!data.data.wind_power) data.data.wind_power = 3200;
        if (!data.data.hydrogen_running_status) data.data.hydrogen_running_status = true;

        // PPC状态变量
        if (!data.data.grid_power) data.data.grid_power = 5000;
        if (!data.data.grid_export_power) data.data.grid_export_power = 12500;
        if (!data.data.grid_import_power) data.data.grid_import_power = 8500;
        if (!data.data.grid_voltage) data.data.grid_voltage = 380;
        if (!data.data.grid_frequency) data.data.grid_frequency = 50.02;

        // 系统采集数据变量
        if (!data.data.wind_power_forecast) data.data.wind_power_forecast = 3500;
        if (!data.data.solar_power_forecast) data.data.solar_power_forecast = 2800;
        if (!data.data.storage_power) data.data.storage_power = 1500;
        if (!data.data.renewable_utilization) data.data.renewable_utilization = 85.6;
        if (!data.data.hydrogen_set_power) data.data.hydrogen_set_power = 4000;
        if (!data.data.hydrogen_real_power) data.data.hydrogen_real_power = 3800;
        if (!data.data.hydrogen_production) data.data.hydrogen_production = 750;
        if (!data.data.green_energy_ratio) data.data.green_energy_ratio = 92.5;
        if (!data.data.system_runtime) data.data.system_runtime = 168;

        // 其他系统参数
        if (!data.data.unit_model) data.data.unit_model = 'H5.X';
        if (!data.data.efficiency) data.data.efficiency = 0.93;
        if (!data.data.daily_production) data.data.daily_production = 9978;
        if (!data.data.daily_power_consumption) data.data.daily_power_consumption = 48275;
        if (!data.data.total_production) data.data.total_production = 68421;
        if (!data.data.total_power_consumption) data.data.total_power_consumption = 310440;
        if (!data.data.stack_voltage) data.data.stack_voltage = 500;
        if (!data.data.ambient_temperature) data.data.ambient_temperature = 28;
        if (!data.data.system_voltage) data.data.system_voltage = 220;
        if (!data.data.auxiliary_voltage) data.data.auxiliary_voltage = 98;

        // 电解槽矩阵数据处理
        // 如果没有电解槽状态数据，创建默认数组
        if (!data.data.electrolyzer_status) {
            data.data.electrolyzer_status = Array(20).fill(0);
            // 设置部分电解槽为不同状态
            for (let i = 0; i < 20; i++) {
                // 随机设置电解槽状态：0 检修 1 运行 2 待机 3 热备 4 冷启动 5 热启动
                data.data.electrolyzer_status[i] = Math.floor(Math.random() * 6);
            }
        }

        // 如果没有电解槽给定功率数据，创建默认数组
        if (!data.data.electrolyzer_set_power) {
            data.data.electrolyzer_set_power = Array(20).fill(0).map((_, i) => {
                // 根据电解槽状态设置给定功率
                // 0 检修 1 运行 2 待机 3 热备 4 冷启动 5 热启动
                const status = data.data.electrolyzer_status[i];
                if (status === 1) return 30 + Math.random() * 20; // 运行状态，正常功率
                if (status === 3) return 10 + Math.random() * 10; // 热备状态，低功率
                if (status === 4 || status === 5) return 5 + Math.random() * 5; // 启动状态，很低功率
                return 0; // 其他状态无功率
            });
        }

        // 如果没有产氢速率数据，创建默认数组
        if (!data.data.hydrogen_rate) {
            data.data.hydrogen_rate = Array(20).fill(0).map((_, i) => {
                const status = data.data.electrolyzer_status[i];
                if (status === 1) return 5 + Math.random() * 5; // 运行状态，正常产氢
                if (status === 3) return 1 + Math.random() * 2; // 热备状态，低产氢
                return 0; // 其他状态无产氢
            });
        }

        // 如果没有电解槽实际功率数据，创建默认数组
        if (!data.data.electrolyzer_real_power) {
            data.data.electrolyzer_real_power = Array(20).fill(0).map((_, i) => {
                const status = data.data.electrolyzer_status[i];

                // 根据状态生成不同范围的功率值（0-5MW）
                if (status === 1) { // 运行状态
                    return 2.5 + Math.random() * 2.5; // 2.5-5MW
                } else if (status === 4) { // 冷启动
                    return 0.5 + Math.random() * 1.5; // 0.5-2MW
                } else if (status === 5) { // 热启动
                    return 1.0 + Math.random() * 2.0; // 1-3MW
                }

                // 其他状态功率为0
                return 0;
            });
        }

        // 如果没有电解槽温度数据，创建默认数组
        if (!data.data.electrolyzer_temp) {
            data.data.electrolyzer_temp = Array(20).fill(0).map((_, i) => {
                const status = data.data.electrolyzer_status[i];
                if (status === 1) return 65 + Math.random() * 15; // 运行状态，高温
                if (status === 3) return 50 + Math.random() * 10; // 热备状态，中等温度
                if (status === 5) return 45 + Math.random() * 10; // 热启动，中等温度
                if (status === 4) return 30 + Math.random() * 10; // 冷启动，低温
                return 25 + Math.random() * 5; // 其他状态，室温
            });
        }
    } else {
        // 非模拟模式下，确保必要的数组字段存在，但不修改其值
        // 仅在数据不存在时初始化为空数组
        if (!data.data.electrolyzer_status) data.data.electrolyzer_status = Array(20).fill(null);
        if (!data.data.electrolyzer_set_power) data.data.electrolyzer_set_power = Array(20).fill(null);
        if (!data.data.hydrogen_rate) data.data.hydrogen_rate = Array(20).fill(null);
        if (!data.data.electrolyzer_real_power) data.data.electrolyzer_real_power = Array(20).fill(null);
        if (!data.data.electrolyzer_temp) data.data.electrolyzer_temp = Array(20).fill(null);
    }

    // 添加到历史数据
    APP_DATA.dataHistory.push(data);

    // 限制历史数据长度 - speed模式下使用更小的缓存
    let maxDataPoints = CONFIG.CHART.MAX_DATA_POINTS;
    if (isSpeedMode && CONFIG.SPEED_MODE && CONFIG.SPEED_MODE.OPTIMIZATIONS) {
        maxDataPoints = CONFIG.SPEED_MODE.OPTIMIZATIONS.MAX_CHART_POINTS || 100;
    }
    
    if (APP_DATA.dataHistory.length > maxDataPoints) {
        APP_DATA.dataHistory = APP_DATA.dataHistory.slice(-maxDataPoints);
    }

    // 调试输出电解槽数据 (仅在调试模式且非speed模式下)
    if (CONFIG.DEBUG && data.data && data.data.electrolyzer_real_power && !isSpeedMode) {
        console.log("电解槽实际功率数据:", data.data.electrolyzer_real_power);
        console.log("电解槽状态数据:", data.data.electrolyzer_status);

        // 调试输出：制氢给定计算
        if (data.data.electrolyzer_set_power) {
            const totalSetPower = data.data.electrolyzer_set_power.reduce((sum, val) => sum + val, 0);
            console.log('电解槽设定功率数组:', data.data.electrolyzer_set_power);
            console.log('电解槽设定功率总和:', totalSetPower.toFixed(2), 'MW');
        }

        // 检查电解槽实际功率数据是否有效
        let validPowerCount = 0;
        let invalidPowerCount = 0;

        for (let i = 0; i < data.data.electrolyzer_real_power.length; i++) {
            const power = data.data.electrolyzer_real_power[i];
            const status = data.data.electrolyzer_status[i];

            if (power !== null && power !== undefined && !isNaN(power)) {
                validPowerCount++;
                console.log(`电解槽 #${i+1} - 状态: ${status}, 功率: ${power} MW`);
            } else {
                invalidPowerCount++;
                console.log(`电解槽 #${i+1} - 状态: ${status}, 功率: 无效`);
            }
        }

        console.log(`有效功率数据: ${validPowerCount}, 无效功率数据: ${invalidPowerCount}`);
    }

    // 更新最新数据
    APP_DATA.latestData = data;
    app.latestData = APP_DATA.latestData;

    // 更新系统状态
    if (data.data && data.data.wind_power > 0 || data.data.solar_power > 0) {
        APP_DATA.systemStatus = '运行中';
    } else {
        APP_DATA.systemStatus = '待机中';
    }
    app.systemStatus = APP_DATA.systemStatus;

    // 如果没有系统信息和设备状态统计数据，则创建
    if (!data.data.system_info) {
        // 计算系统信息
        // 1. 制氢功率 - 基于电解槽实际功率之和
        let hydrogenPower = 0;
        let productionRate = 0;
        let energyConsumption = 0;
        let totalProduction = 0;

        if (data.data.electrolyzer_real_power && data.data.electrolyzer_status && data.data.hydrogen_rate) {
            // 找出所有运行状态的电解槽
            const runningIndices = data.data.electrolyzer_status
                .map((status, index) => (status === 1 ? index : -1))
                .filter(index => index !== -1);

            // 计算运行中电解槽的功率总和
            hydrogenPower = runningIndices
                .reduce((sum, index) => sum + (data.data.electrolyzer_real_power[index] || 0), 0);

            // 计算运行中电解槽的产氢速率总和
            productionRate = runningIndices
                .reduce((sum, index) => sum + (data.data.hydrogen_rate[index] || 0), 0);

            // 计算能耗
            energyConsumption = productionRate > 0 ? hydrogenPower / productionRate : 0;

            // 累计产氢量处理
            if (APP_DATA.useSimulation) {
                // 模拟模式下的累计产氢量计算
                // 如果是首次接收数据，初始化为一个随机值
                if (!APP_DATA.totalProduction) {
                    APP_DATA.totalProduction = 8000 + Math.random() * 2000;
                    APP_DATA.lastTimestamp = data.timestamp || Date.now() / 1000;
                } else {
                    // 计算时间差（小时）
                    const currentTimestamp = data.timestamp || Date.now() / 1000;
                    const hoursDiff = (currentTimestamp - APP_DATA.lastTimestamp) / 3600;

                    // 更新累计产氢量
                    APP_DATA.totalProduction += productionRate * hoursDiff;
                    APP_DATA.lastTimestamp = currentTimestamp;
                }
                totalProduction = APP_DATA.totalProduction;
            } else {
                // 非模拟模式下，使用后端提供的累计产氢量或默认为0
                totalProduction = data.data.total_production || 0;
            }
        }

        // 将计算结果保存到数据中
        data.data.system_info = {
            hydrogen_power: parseFloat(hydrogenPower.toFixed(2)),
            production_rate: parseFloat(productionRate.toFixed(2)),
            energy_consumption: parseFloat(energyConsumption.toFixed(2)),
            total_production: parseFloat(totalProduction.toFixed(2))
        };

        // 计算设备状态统计
        if (data.data.electrolyzer_status) {
            const statusArray = data.data.electrolyzer_status;

            // 计算各状态数量
            const runningCount = statusArray.filter(status => status === 1).length;
            const standbyCount = statusArray.filter(status => status === 2).length;
            const maintenanceCount = statusArray.filter(status => status === 0).length;
            const coldStartCount = statusArray.filter(status => status === 4).length;
            const hotStartCount = statusArray.filter(status => status === 5).length;
            const idleCount = 0; // 默认为0，因为没有对应的状态码

            // 将计算结果保存到数据中
            data.data.device_stats = {
                running_count: runningCount,
                standby_count: standbyCount,
                shutdown_count: 0, // 没有对应的状态码，默认为0
                maintenance_count: maintenanceCount,
                cold_start_count: coldStartCount,
                hot_start_count: hotStartCount,
                idle_count: idleCount
            };
        }
    }

    // --- START of new aggregation logic for power curve chart ---
    if (data.data) {
        // 确保变量对应正确
        const windPower = data.data.wind_power || 0;
        const solarPower = data.data.solar_power || 0;
        const storagePower = data.data.storage_power || 0;
        const hydrogenPower = data.data.hydrogen_power || data.data.hydrogen_real_power || 0;
        const gridPower = data.data.grid_power || 0;

        // 直接将接收到的数据点（无论是1分钟还是15分钟聚合后的）推入图表数据
        MINUTE_POWER_DATA.timestamps.push(new Date(data.timestamp * 1000));
        MINUTE_POWER_DATA.wind_power.push(windPower);
        MINUTE_POWER_DATA.solar_power.push(solarPower);
        MINUTE_POWER_DATA.storage_power.push(storagePower);
        MINUTE_POWER_DATA.hydrogen_power.push(hydrogenPower);
        MINUTE_POWER_DATA.grid_power.push(gridPower);

        // 限制图表显示的数据点数量，例如最近16小时
        // 如果是15分钟一个点，16小时有 16 * 4 = 64个点
        const maxPoints = 16 * (60 / (app.aggregationInfo.minutes || 1));
        if (MINUTE_POWER_DATA.timestamps.length > maxPoints) {
            Object.keys(MINUTE_POWER_DATA).forEach(key => MINUTE_POWER_DATA[key].shift());
        }
    }
    // --- END of new aggregation logic ---

    // 更新图表
    updateCharts(APP_DATA.dataHistory);
}

/**
 * 处理历史数据
 * @param {Array} dataArray - 历史数据数组
 */
function handleHistoryData(dataArray) {
    if (!Array.isArray(dataArray) || dataArray.length === 0) return;

    // 更新历史数据
    APP_DATA.dataHistory = dataArray.slice(-CONFIG.CHART.MAX_DATA_POINTS);

    // 更新最新数据
    APP_DATA.latestData = APP_DATA.dataHistory[APP_DATA.dataHistory.length - 1];
    app.latestData = APP_DATA.latestData;

    // 更新图表
    updateCharts(APP_DATA.dataHistory);
}
