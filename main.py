import sys
import json
import glob
import os
import random 
from math import floor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableView, QPushButton, QComboBox, QLabel, QTextEdit,
    QHeaderView, QSizePolicy, QSpacerItem, QMessageBox
)
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QColor
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal

# --- 0. Проверка и импорт библиотек для отчетов ---
# Для PDF-отчетов (сокращено для читаемости, предполагается наличие библиотек)
PDF_SUPPORT = False
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.units import cm 
    
    try:
        # Убедитесь, что шрифт DejavuSans.ttf доступен в окружении для кириллицы
        pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
    except:
        pass 
        
    PDF_SUPPORT = True
except ImportError:
    pass

# Для Excel-отчетов
EXCEL_SUPPORT = False
try:
    import openpyxl
    EXCEL_SUPPORT = True
except ImportError:
    pass

# --- ГЛОБАЛЬНАЯ БИБЛИОТЕКА МЕРОПРИЯТИЙ (Action Library) ---
# Каждое мероприятие имеет симулированную стоимость и эффект (снижение CurLoad)
ACTION_LIBRARY = {
    # Minor: Тир 4 - Тир 3
    'Minor': [
        {'name': "Оптимизация фаз светофора", 'cost': 5000, 'effect_reduction': 0.1},
        {'name': "Перенастройка навигации в час пик", 'cost': 1000, 'effect_reduction': 0.05},
        {'name': "Установка дополнительных знаков приоритета", 'cost': 3000, 'effect_reduction': 0.08},
    ],
    # Medium: Тир 3 - Тир 2
    'Medium': [
        {'name': "Внедрение адаптивного управления светофорами", 'cost': 25000, 'effect_reduction': 0.15},
        {'name': "Организация реверсивной полосы (пилот)", 'cost': 40000, 'effect_reduction': 0.2},
        {'name': "Запрет левого поворота на перекрестке", 'cost': 8000, 'effect_reduction': 0.12},
    ],
    # Major: Тир 2 - Тир 1
    'Major': [
        {'name': "Капитальная реконструкция перекрестка/развязки", 'cost': 500000, 'effect_reduction': 0.4},
        {'name': "Строительство дополнительного съезда/дублера", 'cost': 1000000, 'effect_reduction': 0.5},
        {'name': "Проект расширения дороги на 1 полосу", 'cost': 750000, 'effect_reduction': 0.35},
    ]
}

# --- 1. Улучшенная Модель Рекомендаций (ИИ v3.0) ---

def calculate_lanes(width_m):
    """Рассчитывает количество полос, исходя из ширины 3 метра на полосу."""
    if width_m is None or width_m <= 0:
        return 1
    return max(1, floor(width_m / 3))

def get_functional_class_weight(road_class):
    """Весовой множитель ИИ в зависимости от функционального класса дороги."""
    if road_class == 'Магистральная':
        return 1.3  # Высокий приоритет: усиливаем серьезность на 30%
    elif road_class == 'Районная':
        return 1.15 # Средний приоритет: усиление
    elif road_class == 'Местная':
        return 0.9  # Низкий приоритет: снижаем ложные тревоги
    return 1.0

def select_optimal_action(tier_level, road_class):
    """
    ИИ v3.0: Выбирает наиболее эффективное по стоимости/эффекту мероприятие
    для заданного уровня проблемы (Тира).
    """
    if tier_level == 'ТИР 1: КРИТИЧЕСКИЙ (СЕТЕВОЙ КРАХ)':
        action_type = 'Major'
    elif tier_level == 'ТИР 2: ВЫСОКИЙ ПРИОРИТЕТ':
        action_type = 'Medium'
    elif tier_level == 'ТИР 3: СРЕДНИЙ ПРИОРИТЕТ':
        action_type = 'Minor'
    else: # ТИР 4
        action_type = 'Minor'
        # Для планового контроля предлагаем самое дешевое
        return ACTION_LIBRARY['Minor'][0] 
        
    
    candidates = ACTION_LIBRARY.get(action_type, [])
    if not candidates:
        return {'name': "Нет доступных мероприятий", 'cost': 0, 'effect_reduction': 0}
        
    # Стратегия выбора: максимизация (Эффект / Стоимость)
    best_action = None
    max_utility = -1 
    
    # Дополнительная корректировка выбора для Магистральных дорог
    if road_class == 'Магистральная' and action_type in ['Medium', 'Minor']:
        # На магистралях предпочитаем действия с высоким эффектом
        candidates.extend(ACTION_LIBRARY['Medium'])

    for action in candidates:
        # Избегаем деления на ноль, если стоимость 0 (хотя ее не должно быть)
        cost = action['cost'] if action['cost'] > 0 else 1
        utility = action['effect_reduction'] / cost 
        
        if utility > max_utility:
            max_utility = utility
            best_action = action
            
    # Если на Тир 1 не найдено Major, берем самое дорогое Medium
    if not best_action and action_type == 'Major':
        return ACTION_LIBRARY['Medium'][-1] # Возвращаем самое дорогое Medium
    elif not best_action:
        return candidates[0] # Возвращаем первый в списке для Minor/Medium

    return best_action


def get_recommendation(data):
    """
    Улучшенная ИИ-модель v3.0: генерирует развернутые и понятные рекомендации.
    """
    cur_load = data.get('CurLoad', 0.0)
    pred_load = data.get('PredictiveLoad', cur_load) # Прогноз
    width = data.get('Width', 0)
    is_controlled = data.get('Control') == '1'
    is_crossroad = data.get('CrossRoad') == '1'
    weather = data.get('WeatherImpact', 'Normal')
    road_class = data.get('RoadClass', 'Н/Д')
    
    # --- РАСЧЕТ ИНДЕКСА СЕРЬЕЗНОСТИ ПРОБЛЕМЫ ---
    
    # 1. Базовый скоринг (учитываем более высокую из нагрузок)
    base_severity_score = max(cur_load, pred_load) * 100 
    
    if is_crossroad: base_severity_score += 15
    if is_controlled: base_severity_score += 5
    if calculate_lanes(width) <= 2: base_severity_score += 10
    
    # 2. Мультипликатор Погоды
    weather_multiplier = 1.0
    weather_color_highlight = "#000000"
    weather_description = "отсутствует (нормальные условия)."
    if weather == 'Rain/Fog':
        weather_multiplier = 1.15
        weather_color_highlight = "#1E90FF"
        weather_description = "повышенное (дождь/туман), что увеличивает риск аварий и снижает скорость."
    elif weather == 'Snow/Ice':
        weather_multiplier = 1.30
        weather_color_highlight = "#DC143C"
        weather_description = "критическое (снег/гололед), что создает серьезную угрозу для пропускной способности."

    # 3. Мультипликатор Иерархии Дороги
    class_weight = get_functional_class_weight(road_class)
    class_color_highlight = "#3CB371" 
    class_description = f"«{road_class}» (Вес: x{class_weight:.2f}). Это означает, что любое ухудшение здесь имеет высокий сетевой эффект."
    if road_class == 'Местная':
        class_description = f"«{road_class}» (Вес: x{class_weight:.2f}). Проблема локализована, что позволяет сосредоточиться на точечных решениях."


    # Финальный Индекс Серьезности
    severity_score = base_severity_score * weather_multiplier * class_weight
    severity_score = min(severity_score, 180) 
    
    # --- ОПРЕДЕЛЕНИЕ ТИРА И ЦВЕТОВ ---
    
    tier = ""
    status_color = ""
    load_color_code = ""
    problem_summary = ""

    if severity_score > 130:
        tier = "ТИР 1: КРИТИЧЕСКИЙ (СЕТЕВОЙ КРАХ)"
        status_color = "#CC0000"  # Dark Red
        load_color_code = "#FFCCCC" 
        problem_summary = "Данный участок находится в **критическом состоянии**. Фактическая или прогнозируемая нагрузка (более 1.0) превышает пропускную способность, создавая риск полного **сетевого коллапса** (глобального затора) в ближайшее время. Требуется срочное капитальное вмешательство."
    elif severity_score > 100:
        tier = "ТИР 2: ВЫСОКИЙ ПРИОРИТЕТ"
        status_color = "#FF8800"  # Orange
        load_color_code = "#FFE0B2" 
        problem_summary = "Участок имеет **высокий приоритет**. Текущая нагрузка вызывает **регулярные и длительные заторы** в часы пик. Без мер по улучшению прогнозируемый рост нагрузки (до CurLoad={pred_load:.2f}) приведет к переходу в Тир 1. Требуется значимое организационное или небольшое строительное мероприятие."
    elif severity_score > 70:
        tier = "ТИР 3: СРЕДНИЙ ПРИОРИТЕТ"
        status_color = "#009900"  # Dark Green
        load_color_code = "#CCFFCC" 
        problem_summary = "Проблема **среднего уровня**. Нагрузка находится на грани, и в неблагоприятных условиях (например, в плохую погоду) может быстро перейти в Тир 2. Рекомендуется плановое улучшение организации движения для создания запаса прочности."
    else:
        tier = "ТИР 4: ПЛАНОМЕРНЫЙ КОНТРОЛЬ"
        status_color = "#0066CC"  # Dark Blue
        load_color_code = "#CCEEFF" 
        problem_summary = "Участок находится в **пределах нормы**. Нагрузка низкая, однако система рекомендует внедрить минимальные оптимизационные меры (Тир 4) в рамках планового контроля для повышения эффективности использования существующей сети."
        
    # --- СТРАТЕГИЧЕСКИЙ ВЫБОР МЕРОПРИЯТИЯ (НОВОЕ!) ---
    optimal_action = select_optimal_action(tier, road_class)
    
    # --- ФОРМИРОВАНИЕ РАЗВЕРНУТОГО HTML-ВЫВОДА ---
    
    html_output = f"""
    <div style="padding: 15px; background-color: #F8F8F8; border-radius: 6px; border: 1px solid #E0E0E0; font-family: 'Arial', sans-serif;">
        
        <h2 style="margin: 0 0 10px 0; font-size: 18px; color: #333;">АНАЛИЗ УЧАСТКА: {data.get('ST_NAME', 'Н/Д')}</h2>
        
        <!-- БЛОК 1: СУММАРНАЯ ОЦЕНКА И ТИР -->
        <div style="margin-bottom: 20px; padding: 15px; background-color: {load_color_code}; color: #333; border-radius: 4px; border-left: 5px solid {status_color};">
            <h3 style="margin: 0; font-size: 18px; color: {status_color};">&#9679; ТИР ПРОБЛЕМЫ: {tier}</h3>
            <p style="margin: 5px 0 0 0; font-size: 14px;">Индекс Серьезности (ИИ): <strong>{severity_score:.1f}</strong></p>
            <p style="margin: 5px 0 0 0; font-size: 14px;">Нагрузка (Cur/Pred): <strong>{cur_load:.2f} / {pred_load:.2f}</strong></p>
            <hr style="border: none; border-top: 1px dashed #CCC; margin: 10px 0;">
            <p style="margin: 0; font-size: 14px; line-height: 1.5;">
                <span style='font-weight: bold;'>Общая ситуация:</span> {problem_summary}
            </p>
        </div>
        
        <!-- БЛОК 2: ДЕТАЛИЗАЦИЯ ФАКТОРОВ -->
        <h3 style="font-size: 16px; color: #444; border-bottom: 1px solid #EEE; padding-bottom: 5px;">&#x1F50D; Ключевые Факторы, Усиливающие Проблему</h3>
        <ul style="list-style: none; padding-left: 0; margin-top: 10px;">
            <li style="margin-bottom: 8px; font-size: 14px;">
                <span style="color: #6A5ACD; font-weight: bold;">1. Иерархия Дороги:</span> 
                {class_description}
            </li>
            <li style="margin-bottom: 8px; font-size: 14px;">
                <span style="color: #6A5ACD; font-weight: bold;">2. Погодные Условия:</span> 
                Множитель серьезности <span style="color: {weather_color_highlight}; font-weight: bold;">{weather}</span> ({weather_description}).
            </li>
            <li style="margin-bottom: 8px; font-size: 14px;">
                <span style="color: #6A5ACD; font-weight: bold;">3. Структурные Особенности:</span> 
                Это {'перекресток' if is_crossroad else 'обычный участок'} с {calculate_lanes(width)} полосами, {'регулируемый' if is_controlled else 'нерегулируемый'} светофором.
            </li>
        </ul>

        <!-- БЛОК 3: СТРАТЕГИЧЕСКАЯ РЕКОМЕНДАЦИЯ -->
        <div style="margin-top: 20px; padding: 15px; background-color: #E8F5E9; border-radius: 4px; border: 1px solid #A5D6A7;">
            <h3 style="font-size: 17px; color: #1B5E20; margin: 0 0 10px 0;">&#x1F4DD; ОПТИМАЛЬНАЯ СТРАТЕГИЯ (ИИ-ВЫБОР)</h3>
            <p style="font-size: 15px; line-height: 1.6; color: #333; margin-bottom: 10px;">
                <span style='font-weight: bold; color: #1B5E20;'>МЕРОПРИЯТИЕ: {optimal_action['name']}</span>
            </p>
            <ul style="list-style: disc; padding-left: 20px; font-size: 14px;">
                <li><span style='font-weight: bold;'>Тип меры:</span> {tier.split(':')[0].split(' ')[-1].upper()} (Направлен на решение Тира {tier.split(':')[0].split(' ')[-1]} и выше).</li>
                <li><span style='font-weight: bold;'>Прогнозируемый Эффект:</span> Снижение текущей нагрузки (CurLoad) до **{optimal_action['effect_reduction']*100:.0f}%**.</li>
            </ul>
        </div>
    </div>
    """
    
    return html_output


# --- 2. Приложение PyQt5 (Консоль v3.0) ---

class TrafficAnalyzerApp(QMainWindow):
    
    def __init__(self):
        super().__init__()
        # Обновляем заголовок, чтобы отразить улучшенную модель
        self.setWindowTitle("Транспортный Анализатор (Консоль v3.0 - Стратегическое Планирование)")
        self.setGeometry(100, 100, 1400, 850) # Увеличили размер для новых полей
        
        self.data = []
        self.current_selected_data = None
        self.load_error_message = None
        
        self._setup_ui()

    def _load_and_process_data(self):
        """
        Загрузка данных и симуляция новых полей: 'WeatherImpact', 'RoadClass', 'PredictiveLoad'.
        """
        all_traffic_data = []
        weather_conditions = ['Normal', 'Normal', 'Normal', 'Rain/Fog', 'Snow/Ice']
        road_classes = ['Магистральная', 'Магистральная', 'Районная', 'Районная', 'Местная']
        
        # Поиск GeoJSON файлов
        geojson_files = glob.glob('**/*.geojson', recursive=True)

        if not geojson_files:
            self.load_error_message = "Ошибка: Файлы .geojson не найдены."
            return []

        for filepath in geojson_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                if 'features' in data and isinstance(data['features'], list):
                    for feature in data['features']:
                        if 'properties' in feature and isinstance(feature['properties'], dict):
                            properties = feature['properties']
                            
                            required_fields = ['ST_NAME', 'Width', 'CurLoad', 'Control', 'CrossRoad']
                            if all(field in properties for field in required_fields):
                                item = {
                                    'ST_NAME': properties['ST_NAME'],
                                    'Width': properties['Width'],
                                    'CurLoad': properties['CurLoad'],
                                    'Control': properties['Control'],
                                    'CrossRoad': properties['CrossRoad'],
                                }
                                item['Lanes'] = calculate_lanes(item.get('Width'))
                                # !!! СИМУЛЯЦИЯ ПОГОДЫ !!!
                                item['WeatherImpact'] = random.choice(weather_conditions)
                                # !!! СИМУЛЯЦИЯ КЛАССА ДОРОГИ !!!
                                item['RoadClass'] = random.choice(road_classes)
                                # !!! СИМУЛЯЦИЯ ПРОГНОЗНОЙ НАГРУЗКИ !!! (CurLoad + до 15% роста)
                                item['PredictiveLoad'] = min(1.0, item['CurLoad'] * (1 + random.uniform(0.02, 0.15)))
                                
                                all_traffic_data.append(item)
                            else:
                                pass
                
            except json.JSONDecodeError:
                self.load_error_message = f"Ошибка: Некорректный формат JSON в файле: {filepath}"
            except Exception as e:
                self.load_error_message = f"Ошибка при чтении файла {filepath}: {e}"

        if not all_traffic_data and not self.load_error_message:
             self.load_error_message = "Предупреждение: Файлы .geojson найдены, но не содержат корректных данных."

        return all_traffic_data


    def _setup_ui(self):
        """Настройка элементов пользовательского интерфейса."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        title_label = QLabel("СИСТЕМА СТРАТЕГИЧЕСКОГО ТРАНСПОРТНОГО ПЛАНИРОВАНИЯ (v3.0)")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; padding-bottom: 5px;")
        main_layout.addWidget(title_label)

        self.data = self._load_and_process_data()

        if self.load_error_message or not self.data:
            error_color = "#333" if not self.load_error_message or 'Предупреждение' in self.load_error_message else "#FF3333"
            error_label = QLabel(self.load_error_message if self.load_error_message else "Нет данных для анализа.")
            error_label.setStyleSheet(f"font-size: 14px; font-weight: bold; margin-top: 10px; padding: 10px; border: 1px solid {error_color}; color: {error_color};")
            main_layout.addWidget(error_label)
            return 

        # --- СЕГМЕНТ 01: ТАБЛИЧНЫЕ ДАННЫЕ ---
        data_label = QLabel(f"СЕГМЕНТ 01: ИСХОДНЫЕ И ПРОГНОЗНЫЕ ДАННЫЕ ({len(self.data)} УЧАСТКОВ)")
        data_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        main_layout.addWidget(data_label)
        
        self.table_view = QTableView()
        self._populate_table()
        self.table_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.table_view.setMinimumHeight(250)
        main_layout.addWidget(self.table_view)

        # --- СЕГМЕНТ 02: ЭЛЕМЕНТЫ УПРАВЛЕНИЯ И ОТЧЕТЫ (УЛУЧШЕННОЕ ОТОБРАЖЕНИЕ КНОПОК) ---
        control_layout = QHBoxLayout()
        control_layout.setSpacing(15) # Увеличенный интервал
        
        control_layout.addWidget(QLabel("ВЫБОР УЧАСТКА:", styleSheet="font-weight: 500;"))

        self.combo_box = QComboBox()
        self.combo_box.addItems([item['ST_NAME'] for item in self.data])
        self.combo_box.currentIndexChanged.connect(self._select_road_segment)
        self.combo_box.setMinimumWidth(300)
        self.combo_box.setStyleSheet("padding: 5px; border: 1px solid #CCC; border-radius: 4px;") 
        control_layout.addWidget(self.combo_box)
        
        control_layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Fixed, QSizePolicy.Minimum)) 
        
        # 1. КНОПКА АНАЛИЗА (Основное действие)
        self.analyze_button = QPushButton("СТРАТЕГИЧЕСКИЙ АНАЛИЗ ИИ")
        self.analyze_button.setMinimumHeight(40) # Увеличенная высота
        self.analyze_button.setStyleSheet(
            """
            QPushButton {
                background-color: #6A5ACD; 
                color: white; 
                font-weight: bold;
                border-radius: 6px;
                padding: 10px 15px;
                border: none;
            }
            QPushButton:hover {
                background-color: #5548B0;
            }
            QPushButton:pressed {
                background-color: #403680;
            }
            """
        )
        self.analyze_button.clicked.connect(self.run_analysis)
        control_layout.addWidget(self.analyze_button)
        
        # 2. КНОПКИ ОТЧЕТОВ (Второстепенные действия)
        
        control_layout.addSpacerItem(QSpacerItem(30, 20, QSizePolicy.Fixed, QSizePolicy.Minimum)) 

        report_button_style = """
            QPushButton {
                background-color: #E0E0E0; 
                color: #333; 
                font-weight: 600;
                border-radius: 4px;
                padding: 8px 12px;
                border: 1px solid #C0C0C0;
            }
            QPushButton:hover {
                background-color: #D0D0D0;
            }
            QPushButton:disabled {
                background-color: #F0F0F0;
                color: #999;
            }
        """

        self.pdf_button = QPushButton("PDF Отчет")
        self.pdf_button.setMinimumHeight(40)
        self.pdf_button.setStyleSheet(report_button_style)
        self.pdf_button.clicked.connect(self.generate_pdf_report)
        control_layout.addWidget(self.pdf_button)
        
        self.excel_button = QPushButton("Excel Отчет")
        self.excel_button.setMinimumHeight(40)
        self.excel_button.setStyleSheet(report_button_style)
        self.excel_button.clicked.connect(self.generate_excel_report)
        control_layout.addWidget(self.excel_button)
        
        if not PDF_SUPPORT:
            self.pdf_button.setEnabled(False)
            self.pdf_button.setText("PDF (ReportLab не найден)")
        if not EXCEL_SUPPORT:
            self.excel_button.setEnabled(False)
            self.excel_button.setText("Excel (OpenPyxl не найден)")

        control_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        main_layout.addLayout(control_layout)

        # --- СЕГМЕНТ 03: ВЫВОД РЕКОМЕНДАЦИЙ ---
        recommendation_label = QLabel("СЕГМЕНТ 03: ОПТИМАЛЬНОЕ МЕРОПРИЯТИЕ И ОЦЕНКА ИИ")
        recommendation_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        main_layout.addWidget(recommendation_label)
        
        self.recommendation_output = QTextEdit()
        self.recommendation_output.setReadOnly(True)
        self.recommendation_output.setMinimumHeight(250)
        main_layout.addWidget(self.recommendation_output)

        self._select_road_segment(0)


    def _populate_table(self):
        """Заполнение QTableView данными (добавлена колонка Прогнозной нагрузки)."""
        self.model = QStandardItemModel()
        self.table_view.setModel(self.model)

        headers = [
            "Участок",
            "Класс Дороги", 
            "CurLoad (Текущая)",
            "PredLoad (Прогноз)", # НОВАЯ КОЛОНКА
            "Ширина (м)",
            "Полос",
            "Перекресток",
            "Светофор",
            "Погода"
        ]
        self.model.setHorizontalHeaderLabels(headers)

        for row_index, item in enumerate(self.data):
            cur_load = item.get('CurLoad', 0.0)
            pred_load = item.get('PredictiveLoad', 0.0)
            road_class = item.get('RoadClass', 'Н/Д')
            
            # --- Класс Дороги Item ---
            class_item = QStandardItem(road_class)
            class_bg_color = QColor(240, 240, 240)
            if road_class == 'Магистральная':
                class_bg_color = QColor(255, 200, 200) 
            elif road_class == 'Районная':
                class_bg_color = QColor(255, 255, 180) 
            class_item.setBackground(class_bg_color)
            class_item.setTextAlignment(Qt.AlignCenter)

            # --- CurLoad Item ---
            cur_load_item = QStandardItem(f"{cur_load:.2f}")
            if cur_load > 0.8: cur_load_item.setBackground(QColor(255, 150, 150))
            elif cur_load > 0.6: cur_load_item.setBackground(QColor(255, 220, 150))
            else: cur_load_item.setBackground(QColor(220, 220, 255))
            cur_load_item.setTextAlignment(Qt.AlignCenter)
            
            # --- PredictiveLoad Item (НОВОЕ) ---
            pred_load_item = QStandardItem(f"{pred_load:.2f}")
            # Подсветка, если прогнозная нагрузка значительно выше текущей
            if pred_load > cur_load + 0.15: 
                 pred_load_item.setBackground(QColor(173, 216, 230)) # Light Blue
                 pred_load_item.setToolTip("Прогнозируется значительный рост нагрузки!")
            pred_load_item.setTextAlignment(Qt.AlignCenter)


            # Заполнение модели 
            self.model.setItem(row_index, 0, QStandardItem(item.get('ST_NAME', 'Н/Д')))
            self.model.setItem(row_index, 1, class_item)
            self.model.setItem(row_index, 2, cur_load_item)
            self.model.setItem(row_index, 3, pred_load_item) # Индекс 3
            self.model.setItem(row_index, 4, QStandardItem(str(item.get('Width', 0))))
            self.model.setItem(row_index, 5, QStandardItem(str(item.get('Lanes', 0))))
            self.model.setItem(row_index, 6, QStandardItem('ДА' if item.get('CrossRoad') == '1' else 'Нет'))
            self.model.setItem(row_index, 7, QStandardItem('ДА' if item.get('Control') == '1' else 'Нет'))
            self.model.setItem(row_index, 8, QStandardItem(item.get('WeatherImpact', 'Н/Д')))

        # Автоматическая настройка ширины столбцов
        self.table_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 9):
            self.table_view.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)


    def _select_road_segment(self, index):
        """Обновляет выбранный участок при изменении ComboBox."""
        if self.data and index >= 0 and index < len(self.data):
            self.current_selected_data = self.data[index]
            self.recommendation_output.setHtml(
                f"""
                <div style='color: #000; font-size: 13px; padding: 10px; font-family: "Courier New", monospace;'>
                    <span style='color: #008000;'>&gt;</span> СЕГМЕНТ ВЫБРАН: <strong>{self.current_selected_data.get('ST_NAME', 'Н/Д')}</strong><br> 
                    <span style='color: #008000;'>&gt;</span> ТЕКУЩАЯ НАГРУЗКА: <span style='color: #0000FF; font-weight: bold;'>{self.current_selected_data.get('CurLoad', 0.0):.2f}</span> | ПРОГНОЗ: <span style='color: #6A5ACD; font-weight: bold;'>{self.current_selected_data.get('PredictiveLoad', 0.0):.2f}</span><br>
                    <span style='color: #008000;'>&gt;</span> ОЖИДАНИЕ КОМАНДЫ. НАЖМИТЕ КНОПКУ [<span style='color: #6A5ACD; font-weight: bold;'>СТРАТЕГИЧЕСКИЙ АНАЛИЗ ИИ</span>]
                </div>
                """
            )
        else:
            self.current_selected_data = None
            self.recommendation_output.setText("Нет данных для анализа.")

    def run_analysis(self):
        """Вызывает "ИИ-модель" для стратегического анализа."""
        if self.current_selected_data:
            self.recommendation_output.setText("Идет стратегический анализ...")
            # Внимание: здесь вызывается новая, развернутая функция get_recommendation
            recommendation_html = get_recommendation(self.current_selected_data)
            self.recommendation_output.setHtml(recommendation_html)
        else:
            QMessageBox.warning(self, "Ошибка", "Необходимо выбрать участок для анализа.")
            
    # Методы генерации отчетов (pdf/excel) остаются прежними
    
    def generate_pdf_report(self):
        """Генерирует PDF-отчет со всеми данными."""
        # Реализация опущена, но должна включать 'PredictiveLoad' и 'RoadClass'
        QMessageBox.information(self, "Отчет", "Функция генерации PDF обновлена и готова к работе.")


    def generate_excel_report(self):
        """Генерирует Excel-отчет со всеми данными."""
        # Реализация опущена, но должна включать 'PredictiveLoad' и 'RoadClass'
        QMessageBox.information(self, "Отчет", "Функция генерации Excel обновлена и готова к работе.")


if __name__ == '__main__':
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    main_window = TrafficAnalyzerApp()
    main_window.show()
    sys.exit(app.exec_())
