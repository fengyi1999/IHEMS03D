/**
 * 图表配置脚本 - 处理所有ECharts图表的初始化和更新
 */

// 获取暗色主题的颜色配置
function getThemeColors() {
    return CONFIG.CHART.DARK_COLORS;
}



// 获取基础图表配置 - 暗色主题
function getBaseChartOption() {
    const colors = getThemeColors();
    
    return {
        backgroundColor: 'transparent',
        textStyle: {
            color: colors.text,
            fontFamily: 'Microsoft YaHei, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            fontSize: 12,
            fontWeight: 400
        },
        grid: {
            left: '3%',
            right: '4%',
            bottom: '8%',
            top: '15%',
            containLabel: true,
            borderColor: colors.grid,
            borderWidth: 1,
            backgroundColor: 'transparent'
        },
        legend: {
            top: '2%',
            left: 'center',
            textStyle: {
                color: colors.text,
                fontSize: 12,
                fontWeight: 500
            },
            itemGap: 20,
            itemWidth: 14,
            itemHeight: 14,
            icon: 'roundRect'
        },
        tooltip: {
            backgroundColor: 'rgba(15, 23, 42, 0.96)',
            borderColor: 'rgba(14, 165, 233, 0.3)',
            borderWidth: 1,
            borderRadius: 8,
            textStyle: {
                color: colors.text,
                fontSize: 12,
                fontWeight: 400
            },
            padding: [12, 16],
            extraCssText: 'box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4), 0 0 20px rgba(14, 165, 233, 0.1); backdrop-filter: blur(20px);'
        },
        // 全局动画配置
        animation: true,
        animationDuration: 1000,
        animationEasing: 'cubicOut',
        animationDelay: function (idx) {
            return idx * 50;
        },
        // 高级视觉效果
        emphasis: {
            focus: 'series',
            blurScope: 'coordinateSystem'
        }
    };
}

// 图表对象集合
const CHARTS = {
    powerCurve: null,
    powerGeneration: null,
    hydrogenLoad: null,
    storage: null,
    batteryState: null
};

// 添加全局变量用于跟踪当前分钟的累计值
let currentMinuteData = {
    windEnergy: 0,
    solarEnergy: 0,
    hydrogenProduction: 0,
    windUtilizationSum: 0,
    solarUtilizationSum: 0,
    utilizationCount: 0,
    lastMinute: null,
    lastSimMinute: null  // 添加仿真分钟跟踪
};

// 添加全局变量用于存储风光利用率分钟平均值
let windUtilizationIntervalAvg = [];
let solarUtilizationIntervalAvg = [];

// 新增：用于发电量统计图表的每小时聚合
let hourlyEnergyData = {
    timestamps: [],
    windEnergy: [],
    solarEnergy: []
};
let tempHourlyEnergy = {
    windEnergy: 0,
    solarEnergy: 0,
    count: 0
};

/**
 * 初始化所有图表
 */
function initCharts() {
    console.log('开始初始化所有图表...');
    
    try {
        // 确保DOM已经加载完成
        if (document.readyState !== 'complete') {
            console.log('DOM未完全加载，等待加载完成...');
            window.addEventListener('load', initCharts);
            return;
        }

        // 获取主题颜色
        const colors = getThemeColors();
        console.log('主题颜色已获取:', colors);

        // 存储图表实例的对象
        const chartInstances = {};

        // 1. 初始化功率曲线图表
        try {
            console.log('初始化功率曲线图表...');
            const powerCurveChart = initPowerCurveChart();
            if (powerCurveChart) {
                chartInstances.powerCurveChart = powerCurveChart;
                CHARTS.powerCurve = powerCurveChart;
                console.log('功率曲线图表初始化成功');
            }
        } catch (error) {
            console.error('功率曲线图表初始化失败:', error);
        }

        // 2. 初始化发电量图表
        try {
            console.log('初始化发电量图表...');
            const powerGenerationChart = initPowerGenerationChart();
            if (powerGenerationChart) {
                chartInstances.powerGenerationChart = powerGenerationChart;
                CHARTS.powerGeneration = powerGenerationChart;
                console.log('发电量图表初始化成功');
            }
        } catch (error) {
            console.error('发电量图表初始化失败:', error);
        }

        // 3. 初始化供氢负载图表
        try {
            console.log('初始化供氢负载图表...');
            const hydrogenLoadChart = initHydrogenLoadChart();
            if (hydrogenLoadChart) {
                chartInstances.hydrogenLoadChart = hydrogenLoadChart;
                CHARTS.hydrogenLoad = hydrogenLoadChart;
                console.log('供氢负载图表初始化成功');
            }
        } catch (error) {
            console.error('供氢负载图表初始化失败:', error);
        }

        // 4. 初始化储氢状态监控图表
        try {
            console.log('初始化储氢状态监控图表...');
            const storageChart = initStorageChart();
            if (storageChart) {
                chartInstances.storageChart = storageChart;
                CHARTS.storage = storageChart;
                console.log('储氢状态监控图表初始化成功');
            }
        } catch (error) {
            console.error('储氢状态监控图表初始化失败:', error);
        }

        // 将图表实例保存到全局对象
        window.CHART_INSTANCES = chartInstances;

        // 绑定窗口大小变化事件
        window.addEventListener('resize', () => {
            Object.values(chartInstances).forEach(chart => {
                if (chart && typeof chart.resize === 'function') {
                    try {
                        chart.resize();
                    } catch (resizeError) {
                        console.warn('图表resize失败:', resizeError);
                    }
                }
            });
        });

        console.log('所有图表初始化完成，成功初始化的图表数量:', Object.keys(chartInstances).length);
        
        // 返回图表实例供外部使用
        return chartInstances;

    } catch (error) {
        console.error('图表初始化过程中发生错误:', error);
        return {};
    }
}

/**
 * 初始化电站功率曲线图
 * @returns {echarts.ECharts} 图表实例
 */
function initPowerCurveChart() {
    // 获取图表DOM容器
    const chartDom = document.getElementById('powerCurveChart');
    if (!chartDom) {
        console.error('找不到图表容器 #powerCurveChart');
        return null;
    }

    // 确保容器有正确的尺寸
    chartDom.style.width = '100%';
    chartDom.style.height = '100%';
    chartDom.style.minHeight = '300px';

    // 初始化ECharts实例
    const chart = echarts.init(chartDom);

    // 获取主题颜色
    const colors = getThemeColors();

    // 图表配置
    const option = {
        backgroundColor: 'transparent',
        animation: true,
        animationDuration: 1000,
        textStyle: {
            color: colors.text,
            fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif'
        },
        title: {
            show: false
        },
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            borderColor: 'rgba(59, 130, 246, 0.3)',
            borderWidth: 1,
            textStyle: {
                color: colors.text,
                fontSize: 12
            },
            padding: [8, 12],
            extraCssText: 'border-radius: 8px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);',
            formatter: function(params) {
                if (!params || params.length === 0) return '';
                let result = params[0].name + '<br/>';
                params.forEach(param => {
                    const value = parseFloat(param.value || 0).toFixed(1);
                    result += param.marker + ' ' + param.seriesName + ': ' + value + ' MW<br/>';
                });
                return result;
            }
        },
        legend: {
            show: false
        },
        grid: {
            left: '4%',
            right: '4%',
            bottom: '8%',
            top: '8%',
            containLabel: true
        },
        xAxis: {
            type: 'category',
            boundaryGap: false,
            data: [],
            axisLine: {
                lineStyle: {
                    color: colors.border,
                    width: 1
                }
            },
            axisTick: {
                show: false
            },
            axisLabel: {
                color: colors.text,
                fontSize: 10,
                interval: 'auto'
            },
            splitLine: {
                show: false
            }
        },
        yAxis: {
            type: 'value',
            min: -100,
            max: 100,
            interval: 25,
            axisLine: {
                show: true,
                lineStyle: {
                    color: colors.border,
                    width: 1
                }
            },
            axisLabel: {
                color: colors.text,
                fontSize: 10,
                formatter: '{value}'
            },
            splitLine: {
                lineStyle: {
                    color: colors.grid,
                    type: 'dashed',
                    width: 1
                }
            }
        },
        series: [
            // === 上部区域：制氢功率和上下网功率 ===
            {
                name: '制氢功率',
                type: 'line',
                smooth: true,
                symbol: 'none',
                itemStyle: {
                    color: colors.chartColors.hydrogen.primary
                },
                lineStyle: {
                    width: 2.5,
                    color: colors.chartColors.hydrogen.primary,
                    cap: 'round'
                },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: colors.chartColors.hydrogen.primary + '60' },
                            { offset: 1, color: colors.chartColors.hydrogen.primary + '10' }
                        ]
                    }
                },
                data: [],
                emphasis: {
                    focus: 'series',
                    lineStyle: {
                        width: 3
                    }
                },
                z: 4 // 最高层级
            },
            {
                name: '上下网功率',
                type: 'line',
                smooth: true,
                symbol: 'none',
                itemStyle: {
                    color: colors.chartColors.grid.primary
                },
                lineStyle: {
                    width: 2.5,
                    color: colors.chartColors.grid.primary,
                    cap: 'round'
                },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: colors.chartColors.grid.primary + '60' },
                            { offset: 1, color: colors.chartColors.grid.primary + '10' }
                        ]
                    }
                },
                data: [],
                emphasis: {
                    focus: 'series',
                    lineStyle: {
                        width: 3
                    }
                },
                z: 3 // 第二层级
            },
            // === 下部区域：风电功率和光伏功率（取反显示） ===
            {
                name: '风电功率',
                type: 'line',
                smooth: true,
                symbol: 'none',
                itemStyle: {
                    color: colors.chartColors.wind.primary
                },
                lineStyle: {
                    width: 2.5,
                    color: colors.chartColors.wind.primary,
                    cap: 'round'
                },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: colors.chartColors.wind.primary + '10' },
                            { offset: 1, color: colors.chartColors.wind.primary + '60' }
                        ]
                    }
                },
                data: [],
                emphasis: {
                    focus: 'series',
                    lineStyle: {
                        width: 3
                    }
                },
                z: 2 // 第三层级
            },
            {
                name: '光伏功率',
                type: 'line',
                smooth: true,
                symbol: 'none',
                itemStyle: {
                    color: colors.chartColors.solar.primary
                },
                lineStyle: {
                    width: 2.5,
                    color: colors.chartColors.solar.primary,
                    cap: 'round'
                },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: colors.chartColors.solar.primary + '10' },
                            { offset: 1, color: colors.chartColors.solar.primary + '60' }
                        ]
                    }
                },
                data: [],
                emphasis: {
                    focus: 'series',
                    lineStyle: {
                        width: 3
                    }
                },
                z: 1 // 最底层级
            },
            {
                name: '储能功率',
                type: 'line',
                smooth: true,
                symbol: 'none',
                itemStyle: {
                    color: colors.chartColors.storage.primary
                },
                lineStyle: {
                    width: 2.5,
                    color: colors.chartColors.storage.primary,
                    cap: 'round'
                },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: colors.chartColors.storage.primary + '60' },
                            { offset: 1, color: colors.chartColors.storage.primary + '10' }
                        ]
                    }
                },
                data: [],
                emphasis: {
                    focus: 'series',
                    lineStyle: {
                        width: 3
                    }
                },
                z: 2.5 // 中间层级
            }
        ]
    };

    // 设置图表配置并渲染
    chart.setOption(option);

    // 监听容器大小变化
    const resizeObserver = new ResizeObserver(() => {
        chart.resize();
    });
    resizeObserver.observe(chartDom);

    console.log('功率曲线图表初始化完成');
    return chart;
}

/**
 * 初始化电池状态图表
 * @returns {echarts.ECharts} 图表实例
 */
function initBatteryStateChart() {
    // 获取图表DOM容器
    const chartDom = document.getElementById('batteryStateChart');
    if (!chartDom) return null;

    // 初始化ECharts实例，使用容器的宽高
    const chart = echarts.init(chartDom);
    // 确保图表填充满容器
    setTimeout(() => {
        chart.resize();
    }, 50);

    // 设置初始空数据
    const socData = [];
    const timeData = [];

    // 获取主题颜色
    const colors = getThemeColors();
    const baseOption = getBaseChartOption();

    // 图表配置项
    const option = {
        title: {
            show: false
        },
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'line'
            },

            backgroundColor: 'rgba(13, 42, 66, 0.8)',
            borderColor: '#00aeff',
            textStyle: {
                color: '#fff'
            }
        },
        legend: {
            show: false
        },
        grid: {
            left: '3%',
            right: '3%',
            bottom: '3%',
            top: '10%',
            containLabel: true
        },
        xAxis: {
            type: 'category',
            boundaryGap: false,
            data: timeData,
            axisLine: {
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.2)'
                }
            },
            axisTick: {
                show: false
            },
            axisLabel: {
                color: 'rgba(255, 255, 255, 0.6)',
                fontSize: 10
            },
            splitLine: {
                show: true,
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.08)'
                }
            }
        },
        yAxis: {
            type: 'value',
            name: '%',
            nameGap: 5,
            nameTextStyle: {
                color: 'rgba(255, 255, 255, 0.6)',
                padding: [0, 0, 0, -5],
                fontSize: 10
            },
            min: 0,
            max: 100,
            interval: 20,
            axisLine: {
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.2)'
                }
            },
            axisTick: {
                show: false
            },
            axisLabel: {
                color: 'rgba(255, 255, 255, 0.6)',
                fontSize: 10
            },
            splitLine: {
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.08)'
                }
            }
        },
        series: [
            {
                name: '电池充电量',
                type: 'line',
                smooth: true,
                symbol: 'none',
                data: socData,
                itemStyle: {
                    color: colors.chartColors.storage.primary,
                    shadowColor: colors.chartColors.storage.glow,
                    shadowBlur: 10
                },
                lineStyle: {
                    width: 3,
                    shadowColor: colors.chartColors.storage.glow,
                    shadowBlur: 8
                },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, colors.chartColors.storageGradient)
                }
            }
        ]
    };

    // 使用配置项设置图表
    chart.setOption(option);

    return chart;
}

/**
 * 初始化发电量统计图表
 * @returns {echarts.ECharts} 图表实例
 */
function initPowerGenerationChart() {
    const chartDom = document.getElementById('powerGenerationChart');
    if (!chartDom) {
        console.error('找不到图表容器 #powerGenerationChart');
        return null;
    }

    // 确保容器有正确的尺寸
    chartDom.style.width = '100%';
    chartDom.style.height = '100%';
    chartDom.style.minHeight = '260px';

    const chart = echarts.init(chartDom);
    const colors = getThemeColors();

    const option = {
        backgroundColor: 'transparent',
        animation: true,
        animationDuration: 1000,
        textStyle: {
            color: colors.text,
            fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif'
        },
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            borderColor: 'rgba(59, 130, 246, 0.3)',
            borderWidth: 1,
            textStyle: {
                color: colors.text,
                fontSize: 12
            },
            padding: [8, 12],
            extraCssText: 'border-radius: 8px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);',
            formatter: function(params) {
                if (!params || params.length === 0) return '';
                let result = params[0].name + '<br/>';
                params.forEach(param => {
                    const value = parseFloat(param.value || 0).toFixed(1);
                    result += param.marker + ' ' + param.seriesName + ': ' + value + ' MWh<br/>';
                });
                return result;
            }
        },
        legend: {
            show: true,
            bottom: '8%',
            textStyle: {
                color: colors.text,
                fontSize: 11
            },
            itemWidth: 16,
            itemHeight: 8
        },
        grid: {
            left: '8%',
            right: '4%',
            bottom: '20%',
            top: '8%',
            containLabel: true
        },
        xAxis: {
            type: 'category',
            data: [],
            axisLine: {
                lineStyle: {
                    color: colors.border,
                    width: 1
                }
            },
            axisTick: {
                show: false
            },
            axisLabel: {
                color: colors.text,
                fontSize: 10
            },
            splitLine: {
                show: false
            }
        },
        yAxis: {
            type: 'value',
            name: 'MWh',
            nameTextStyle: {
                color: colors.text,
                fontSize: 10
            },
            axisLine: {
                show: true,
                lineStyle: {
                    color: colors.border,
                    width: 1
                }
            },
            axisLabel: {
                color: colors.text,
                fontSize: 10,
                formatter: '{value}'
            },
            splitLine: {
                lineStyle: {
                    color: colors.grid,
                    type: 'dashed',
                    width: 1
                }
            }
        },
        series: [
            {
                name: '风电发电量',
                type: 'bar',
                stack: 'total',
                barWidth: '100%', // 占满分类宽度
                barGap: '0%', // 无间隙
                barCategoryGap: '0%', // 无分类间隙
                data: [...windEnergyIntervalMWh, currentMinuteData.windEnergy].slice(-30), // 最多显示30根柱子
                itemStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: '#92BFFF' }, // 指定的蓝色
                        { offset: 1, color: '#6FA8F5' }  // 稍深一点的蓝色
                    ]),
                    shadowColor: 'rgba(146, 191, 255, 0.4)',
                    shadowBlur: 6,
                    borderRadius: [4, 4, 0, 0]
                },
                emphasis: {
                    itemStyle: {
                        shadowBlur: 12,
                        shadowColor: 'rgba(146, 191, 255, 0.5)'
                    }
                }
            },
            {
                name: '光伏发电量',
                type: 'bar',
                stack: 'total',
                barWidth: '100%', // 占满分类宽度
                barGap: '0%', // 无间隙
                barCategoryGap: '0%', // 无分类间隙
                data: [...solarEnergyIntervalMWh, currentMinuteData.solarEnergy].slice(-30), // 最多显示30根柱子
                itemStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(96, 165, 250, 1)' }, // Android柱子浅蓝色
                        { offset: 1, color: 'rgba(59, 130, 246, 1)' }  // 更深的蓝色
                    ]),
                    shadowColor: 'rgba(59, 130, 246, 0.4)',
                    shadowBlur: 6,
                    borderRadius: [0, 0, 0, 0]
                },
                emphasis: {
                    itemStyle: {
                        shadowBlur: 12,
                        shadowColor: 'rgba(59, 130, 246, 0.5)'
                    }
                }
            }
        ]
    };

    chart.setOption(option);

    // 监听容器大小变化
    const resizeObserver = new ResizeObserver(() => {
        chart.resize();
    });
    resizeObserver.observe(chartDom);

    console.log('发电量图表初始化完成');
    return chart;
}

/**
 * 初始化供氢负载统计图表
 * @returns {echarts.ECharts} 图表实例
 */
function initHydrogenLoadChart() {
    const chartDom = document.getElementById('hydrogenLoadChart');
    if (!chartDom) {
        console.error('找不到图表容器 #hydrogenLoadChart');
        return null;
    }

    // 确保容器有正确的尺寸
    chartDom.style.width = '100%';
    chartDom.style.height = '100%';
    chartDom.style.minHeight = '260px';

    const chart = echarts.init(chartDom);
    const colors = getThemeColors();

    const option = {
        backgroundColor: 'transparent',
        animation: true,
        animationDuration: 1000,
        textStyle: {
            color: colors.text,
            fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif'
        },
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            borderColor: 'rgba(16, 185, 129, 0.3)',
            borderWidth: 1,
            textStyle: {
                color: colors.text,
                fontSize: 12
            },
            padding: [8, 12],
            extraCssText: 'border-radius: 8px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);',
            formatter: function(params) {
                if (!params || params.length === 0) return '';
                let result = params[0].name + '<br/>';
                params.forEach(param => {
                    const value = parseFloat(param.value || 0).toFixed(2);
                    result += param.marker + ' ' + param.seriesName + ': ' + value + ' Nm³/h<br/>';
                });
                return result;
            }
        },
        legend: {
            show: false
        },
        grid: {
            left: '8%',
            right: '4%',
            bottom: '8%',
            top: '8%',
            containLabel: true
        },
        xAxis: {
            type: 'category',
            data: [],
            axisLine: {
                lineStyle: {
                    color: colors.border,
                    width: 1
                }
            },
            axisTick: {
                show: false
            },
            axisLabel: {
                color: colors.text,
                fontSize: 10
            },
            splitLine: {
                show: false
            }
        },
        yAxis: {
            type: 'value',
            name: 'Nm³/h',
            nameTextStyle: {
                color: colors.text,
                fontSize: 10
            },
            axisLine: {
                show: true,
                lineStyle: {
                    color: colors.border,
                    width: 1
                }
            },
            axisLabel: {
                color: colors.text,
                fontSize: 10,
                formatter: '{value}'
            },
            splitLine: {
                lineStyle: {
                    color: colors.grid,
                    type: 'dashed',
                    width: 1
                }
            }
        },
        series: [
            {
                name: '供氢负载',
                type: 'bar',
                barWidth: '100%',
                barGap: '0%',
                barCategoryGap: '0%',
                data: [],
                itemStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: '#96E2D6' },
                        { offset: 1, color: '#7DD3C0' }
                    ]),
                    shadowColor: 'rgba(150, 226, 214, 0.4)',
                    shadowBlur: 8,
                    borderWidth: 0,
                    borderRadius: [6, 6, 0, 0]
                },
                emphasis: {
                    itemStyle: {
                        shadowBlur: 15,
                        shadowColor: 'rgba(150, 226, 214, 0.5)',
                        borderWidth: 0
                    }
                }
            }
        ]
    };

    chart.setOption(option);

    // 监听容器大小变化
    const resizeObserver = new ResizeObserver(() => {
        chart.resize();
    });
    resizeObserver.observe(chartDom);

    console.log('供氢负载图表初始化完成');
    return chart;
}

/**
 * 初始化储氢状态监控图表
 * @returns {echarts.ECharts} 图表实例
 */
function initStorageChart() {
    const chartDom = document.getElementById('storageChart');
    if (!chartDom) {
        console.error('找不到图表容器 #storageChart');
        return null;
    }

    // 确保容器有正确的尺寸
    chartDom.style.width = '100%';
    chartDom.style.height = '100%';
    chartDom.style.minHeight = '260px';

    const chart = echarts.init(chartDom);
    const colors = getThemeColors();

    const option = {
        backgroundColor: 'transparent',
        animation: true,
        textStyle: { color: colors.text, fontFamily: 'Inter, sans-serif' },
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            borderColor: 'rgba(59, 130, 246, 0.3)',
            textStyle: { color: colors.text, fontSize: 12 },
            formatter: function(params) {
                if (!params || params.length === 0) return '';
                let result = params[0].name + '<br/>';
                params.forEach(param => {
                    const value = parseFloat(param.value || 0).toFixed(2);
                    let unit = '';
                    if (param.seriesName === '储氢SOH') {
                        unit = ' %';
                    } else if (param.seriesName === '充放速率') {
                        unit = ' Nm³/h';
                    }
                    result += param.marker + ' ' + param.seriesName + ': ' + value + unit + '<br/>';
                });
                return result;
            }
        },
        legend: {
            data: ['储氢SOH', '充放速率'],
            textStyle: { color: colors.text, fontSize: 11 },
            bottom: '8%',
        },
        grid: { left: '8%', right: '8%', bottom: '20%', top: '15%', containLabel: true },
        xAxis: {
            type: 'category',
            data: [],
            axisLine: { lineStyle: { color: colors.border } },
            axisLabel: { color: colors.text, fontSize: 10 },
        },
        yAxis: [
            {
                type: 'value',
                name: 'SOH (%)',
                position: 'left',
                axisLine: { show: true, lineStyle: { color: colors.chartColors.storage.primary } },
                axisLabel: { color: colors.chartColors.storage.primary, fontSize: 10 },
                splitLine: { show: false },
            },
            {
                type: 'value',
                name: '速率 (Nm³/h)',
                position: 'right',
                axisLine: { show: true, lineStyle: { color: colors.chartColors.hydrogen.primary } },
                axisLabel: { color: colors.chartColors.hydrogen.primary, fontSize: 10 },
                splitLine: { show: false },
            }
        ],
        series: [
            {
                name: '储氢SOH',
                type: 'line',
                smooth: true,
                yAxisIndex: 0,
                data: [],
                itemStyle: { color: colors.chartColors.storage.primary },
            },
            {
                name: '充放速率',
                type: 'line',
                smooth: true,
                yAxisIndex: 1,
                data: [],
                itemStyle: { color: colors.chartColors.hydrogen.primary },
                markLine: {
                    silent: true,
                    symbol: 'none',
                    lineStyle: {
                        type: 'dashed',
                        color: colors.text
                    },
                    data: [{ yAxis: 0, label: { show: false } }],
                    emphasis: { disabled: true }
                }
            }
        ]
    };

    chart.setOption(option);
    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(chartDom);
    console.log('储氢状态监控图表初始化完成');
    return chart;
}

// 定义全局变量用于存储能源数据
let windEnergyIntervalMWh = [];
let solarEnergyIntervalMWh = [];
let hydrogenIntervalNm3 = [];

/**
 * 更新所有图表的数据
 * @param {Array} dataHistory - 历史数据数组
 */
function updateCharts(dataHistory) {
    if (!Array.isArray(dataHistory) || dataHistory.length === 0) return;

    const aggregationMinutes = app.aggregationInfo ? app.aggregationInfo.minutes : 1;
    const latestDataPoint = dataHistory[dataHistory.length - 1];

    // --- 实时功率监控图表 ---
    if (CHARTS.powerCurve) {
        const powerCurveTimeLabels = MINUTE_POWER_DATA.timestamps.map(ts => {
            const date = new Date(ts);
            // 创建仿真时间标签，例如 11:00, 11:15, 11:30
            return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
        });

        const hydrogenPowerData = MINUTE_POWER_DATA.hydrogen_power.map(v => v.toFixed(2));
        const gridPowerData = MINUTE_POWER_DATA.grid_power.map(v => v.toFixed(2));
        const windPowerData = MINUTE_POWER_DATA.wind_power.map(v => (-Math.abs(v)).toFixed(2));
        const solarPowerData = MINUTE_POWER_DATA.solar_power.map(v => (-Math.abs(v)).toFixed(2));
        const storagePowerData = MINUTE_POWER_DATA.storage_power.map(v => v.toFixed(2));

        CHARTS.powerCurve.setOption({
            xAxis: {
                data: powerCurveTimeLabels,
                axisLabel: {
                    interval: (index, value) => {
                        // 每4个点（即每小时）显示一个标签
                        return index % 4 === 0;
                    }
                }
            },
            series: [
                { name: '制氢功率', data: hydrogenPowerData },
                { name: '上下网功率', data: gridPowerData },
                { name: '风电功率', data: windPowerData },
                { name: '光伏功率', data: solarPowerData },
                { name: '储能功率', data: storagePowerData }
            ]
        });
    }

    // --- 发电量统计图表 ---
    if (CHARTS.powerGeneration) {
        const energyTimeLabels = [];
        const windEnergyData = [];
        const solarEnergyData = [];
        
        // 每个点是15分钟的平均功率，转换为15分钟的发电量
        const intervalHours = (aggregationMinutes || 15) / 60.0;

        for (let i = 0; i < MINUTE_POWER_DATA.timestamps.length; i++) {
            const ts = MINUTE_POWER_DATA.timestamps[i];
            const date = new Date(ts);
            const timeLabel = `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
            energyTimeLabels.push(timeLabel);

            windEnergyData.push((MINUTE_POWER_DATA.wind_power[i] * intervalHours).toFixed(3));
            solarEnergyData.push((MINUTE_POWER_DATA.solar_power[i] * intervalHours).toFixed(3));
        }

        CHARTS.powerGeneration.setOption({
            xAxis: {
                data: energyTimeLabels,
                axisLabel: {
                    interval: (index, value) => {
                        // 每4个点（即每小时）显示一个标签
                        return index % 4 === 0;
                    }
                }
            },
            series: [
                { name: '风电发电量', data: windEnergyData },
                { name: '光伏发电量', data: solarEnergyData }
            ]
        });
    }

    // --- 其他图表 (保持不变) ---
    const timeData = dataHistory.map(item => {
        const date = new Date(item.timestamp * 1000);
        return `${date.getHours()}:${date.getMinutes().toString().padStart(2, '0')}`;
    });

    if (CHARTS.hydrogenLoad && latestDataPoint.data.hydrogen_load !== undefined) {
        const hydrogenLoadData = dataHistory.map(item => (item.data.hydrogen_load || 0).toFixed(2));
        CHARTS.hydrogenLoad.setOption({
            xAxis: { data: timeData },
            series: [{ data: hydrogenLoadData }]
        });
    }

    if (CHARTS.storage && latestDataPoint.data.hydrogen_soc !== undefined && latestDataPoint.data.hydrogen_hss !== undefined) {
        const socData = dataHistory.map(item => ((item.data.hydrogen_soc || 0) * 100).toFixed(1));
        const hssData = dataHistory.map(item => (item.data.hydrogen_hss || 0).toFixed(2));
        CHARTS.storage.setOption({
            xAxis: { data: timeData },
            series: [
                { name: '储氢SOH', data: socData },
                { name: '充放速率', data: hssData }
            ]
        });
    }

    // 强制所有图表重新调整大小，确保充满容器
    setTimeout(() => {
        Object.values(CHARTS).forEach(chart => {
            if (chart) {
                chart.resize();
            }
        });
    }, 100);
}
