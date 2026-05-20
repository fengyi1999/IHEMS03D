#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
图表生成器模块
用于生成各种图表的配置
"""

import time
import random
import math
from datetime import datetime

class ChartGenerator:
    """图表生成器类"""
    
    @staticmethod
    def generate_variable_chart(variables_data_dict, main_title=None):
        """
        生成变量趋势图表配置
        
        Args:
            variables_data_dict: 变量数据字典，格式为 {变量名: [{timestamp: 时间戳, value: 值}, ...], ...}
            main_title: 图表主标题 (不再使用)
            
        Returns:
            dict: ECharts配置对象
        """
        if not variables_data_dict:
            return {
                "tooltip": {"trigger": "axis"},
                "legend": {"data": []},
                "xAxis": {"type": "time", "data": []},
                "yAxis": {"type": "value"},
                "series": []
            }
        
        # 提取所有变量名
        variable_names = list(variables_data_dict.keys())
        
        # 创建系列数据和y轴配置
        series = []
        yAxis = []
        
        # 始终使用多y轴 (变量数量 > 1)
        use_multi_axis = len(variable_names) > 1
        
        # 防止重复添加相同变量
        processed_vars = set()
        
        for index, variable_name in enumerate(variable_names):
            # 跳过重复的变量
            if variable_name in processed_vars:
                continue
            
            processed_vars.add(variable_name)
            
            # 获取变量数据
            variable_data = variables_data_dict[variable_name]
            
            # 如果数据为空，跳过
            if not variable_data:
                continue
            
            # 提取时间和值
            data_points = []
            values = []  # 用于计算值的范围
            
            for point in variable_data:
                # 确保时间戳是毫秒级的
                timestamp = point.get('timestamp', 0) * 1000  # 转换为毫秒
                value = point.get('value', None)
                
                if value is not None:
                    data_points.append([timestamp, value])
                    values.append(value)
            
            # 按时间排序
            data_points.sort(key=lambda x: x[0])
            
            # 如果使用多轴，为每个变量创建独立的Y轴
            if use_multi_axis:
                # 创建独立的Y轴配置
                y_axis_index = len(yAxis)  # 使用已添加的y轴数量作为索引
                
                # 计算合适的值范围
                if values:
                    min_value = min(values)
                    max_value = max(values)
                    
                    # 增加一些边距，使图表更美观
                    range_pad = (max_value - min_value) * 0.1 if max_value > min_value else (abs(max_value) * 0.1 if max_value != 0 else 1)
                    y_min = min_value - range_pad
                    y_max = max_value + range_pad
                    
                    # 根据值的特性调整y轴位置
                    position = "left" if y_axis_index % 2 == 0 else "right"
                    offset = 50 * (y_axis_index // 2) if position == "left" else 50 * ((y_axis_index - 1) // 2)
                    
                    # 创建格式化函数的代码字符串
                    formatter_code = """
                    function (value) {
                        if (Math.abs(value) >= 100) {
                            return value.toFixed(0);
                        } else if (Math.abs(value) >= 10) {
                            return value.toFixed(1);
                        } else if (Math.abs(value) >= 1) {
                            return value.toFixed(2);
                        } else {
                            return value.toFixed(3);
                        }
                    }
                    """
                    
                    yAxis.append({
                        "type": "value",
                        "name": variable_name,
                        "position": position,
                        "offset": offset,
                        "min": y_min,
                        "max": y_max,
                        "nameTextStyle": {
                            "color": "#fff",
                            "width": 60,            # 设置文本宽度
                            "overflow": "break",    # 文本溢出时换行
                            "lineHeight": 16,       # 行高
                            "rich": {               # 富文本配置
                                "a": {
                                    "width": 60,
                                    "lineHeight": 16
                                }
                            }
                        },
                        "axisLabel": {
                            "formatter": formatter_code.strip(),
                            "color": "#8392A5"
                        },
                        "axisLine": {
                            "lineStyle": {
                                "color": "#8392A5"
                            }
                        },
                        "splitLine": {
                            "show": True,
                            "lineStyle": {
                                "color": "#0d2a42"
                            }
                        }
                    })
                
                # 创建系列，指定使用对应的Y轴
                series_item = {
                    "name": variable_name,
                    "type": "line",
                    "showSymbol": False,
                    "data": data_points,
                    "smooth": True,
                    "yAxisIndex": y_axis_index,
                    "lineStyle": {
                        "width": 2
                    }
                }
            else:
                # 单轴模式，所有变量共用一个Y轴
                series_item = {
                    "name": variable_name,
                    "type": "line",
                    "showSymbol": False,
                    "data": data_points,
                    "smooth": True,
                    "lineStyle": {
                        "width": 2
                    }
                }
            
            series.append(series_item)
        
        # 如果没有多轴，使用默认Y轴配置
        if not use_multi_axis or not yAxis:
            yAxis = {
                "type": "value",
                "axisLine": {
                    "lineStyle": {
                        "color": "#8392A5"
                    }
                },
                "splitLine": {
                    "show": True,
                    "lineStyle": {
                        "color": "#0d2a42"
                    }
                }
            }
        
        # 调整图表边距，确保有足够空间显示所有元素
        grid_right = "2%"
        grid_left = "2%"
        
        if use_multi_axis:
            if len(processed_vars) > 4:
                # 当变量数量大于4时，增加右侧边距
                right_vars = sum(1 for i, _ in enumerate(processed_vars) if i % 2 == 1)
                grid_right = f"{2 + right_vars * 5}%"
                
                # 同时增加左侧边距
                left_vars = sum(1 for i, _ in enumerate(processed_vars) if i % 2 == 0)
                grid_left = f"{2 + left_vars * 2}%"
            else:
                # 少量变量时的边距调整
                grid_right = "5%"
                grid_left = "5%"
        
        # 对图例进行分组和包装
        legend_data = list(processed_vars)
        
        # 创建图表配置
        chart_option = {
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {
                    "type": "cross",
                    "label": {
                        "backgroundColor": "#6a7985"
                    }
                }
            },
            "legend": {
                "data": legend_data,
                "textStyle": {
                    "color": "#fff",
                    "width": 120,
                    "overflow": "truncate"  # 超出宽度时截断
                },
                "formatter": "{b}",  # 使用默认格式化，在前端处理长文本
                "top": 10,
                "type": "scroll",  # 允许滚动
                "pageButtonPosition": "end",
                "pageButtonGap": 5
            },
            "grid": {
                "left": grid_left,
                "right": grid_right,
                "bottom": "35px",
                "top": "40px",
                "containLabel": True
            },
            "xAxis": {
                "type": "time",
                "axisLine": {
                    "lineStyle": {
                        "color": "#8392A5"
                    }
                },
                "splitLine": {
                    "show": False
                }
            },
            "yAxis": yAxis,
            "series": series,
            "color": ["#00aeff", "#ff7b00", "#7cffb2", "#fddd60", "#ff6e76", "#58d9f9", "#05c091", "#7d7ee8"],
            "backgroundColor": "rgba(0,0,0,0)",
            "textStyle": {
                "color": "#fff"
            },
            "dataZoom": [
                {
                    "type": "inside",
                    "start": 0,
                    "end": 100
                },
                {
                    "type": "slider",
                    "start": 0,
                    "end": 100,
                    "height": 30,
                    "bottom": 5,
                    "borderColor": "transparent",
                    "backgroundColor": "rgba(13, 42, 66, 0.8)",
                    "fillerColor": "rgba(0, 174, 255, 0.2)",
                    "handleStyle": {
                        "color": "#00aeff",
                        "borderColor": "#00aeff"
                    },
                    "textStyle": {
                        "color": "#fff"
                    }
                }
            ]
        }
        
        return chart_option
    
    @staticmethod
    def calculate_statistics(variable_data):
        """
        计算变量数据的统计信息
        
        Args:
            variable_data: 变量数据列表，格式为 [{timestamp: 时间戳, value: 值}, ...]
            
        Returns:
            dict: 统计信息，包括最大值、最小值、平均值、标准差等
        """
        if not variable_data:
            return {
                "max": None,
                "min": None,
                "avg": None,
                "std": None,
                "count": 0
            }
        
        # 提取值
        values = [point.get('value', 0) for point in variable_data if point.get('value') is not None]
        
        if not values:
            return {
                "max": None,
                "min": None,
                "avg": None,
                "std": None,
                "count": 0
            }
        
        # 计算统计信息
        max_value = max(values)
        min_value = min(values)
        avg_value = sum(values) / len(values)
        
        # 计算标准差
        variance = sum((x - avg_value) ** 2 for x in values) / len(values)
        std_value = math.sqrt(variance)
        
        return {
            "max": max_value,
            "min": min_value,
            "avg": avg_value,
            "std": std_value,
            "count": len(values)
        }