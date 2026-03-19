import re
import json
from io import BytesIO
from typing import List
from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from aigw_ct.context import APP_CTX

logger = APP_CTX.get_logger()

class DocumentProcessingHelpers:
    """Класс для помощи в обработке документов"""
    
    """
    Основные методы:
        extract_text: Извлечение текста документа из байтового массива
        precise_trim_docx: Разделение документа на текст и формы по регулярному выражению
        precise_trim_forms: Извлечение форм из документа по регулярным выражениям начала и конца в новый байт-массив
    """

    def __init__(self, bytes_array, split_phrase=None):
        self.bytes_array = bytes_array
        self.split_phrase = split_phrase
        bitt = bytes(int(b) for b in self.bytes_array)
        self.doc = Document(BytesIO(bitt))

    def _contains_text_forms(self, element, text):
        """Проверка наличия регулярного выражения в тексте элемента"""
        if isinstance(element, Paragraph):
            return self._clear_text(text) in self._clear_text(element.text)
        elif isinstance(element, Table):
            for row in element.rows:
                for cell in row.cells:
                    if self._clear_text(text) in self._clear_text(cell.text):
                        return True
        return False

    def _clear_text(self, text):
        """Отчистка текста от всего кроме букв"""
        text = text.lower()
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^a-zA-Zа-яА-ЯёЁ0-9]', '', text)
        return text

    def extract_text(self) -> str:
        doc = self.doc
        result = []
        for el in doc.iter_inner_content():

            if el._element.tag.endswith('p'):
                if el.text != '':
                    text = el.text.strip()
                    text = re.sub(r'\s{3,}', '\n', text)
                    result.append(text)
                    result.append('\n')
            elif el._element.tag.endswith('tbl'):
                table = []
                result.append('******Начало таблицы******\n')
                for row in el.rows:
                    for cell in row.cells:
                        text = cell.text
                        text = re.sub('\n', ' ', text)
                        text = re.sub(r'\s+', ' ', text)
                        if text == '':
                            table.append('Пустая ячейка')
                            continue
                        table.append(text.strip())
                    table.append('\n')
                result.append(f"|{'|'.join(table)}")
                result.append('******Конец таблицы******\n\n')
        return ''.join(result)

    def precise_trim_docx(self) -> tuple([str, List[bytes]]):
        """
        Удаляет ВСЕ элементы документа до элемента с start_text
        и ВСЕ элементы после элемента с end_text.
        Сохраняет результат в новый файл.
        """
        doc = self.doc
        start_text = self.split_phrase.lower()
        start_text = re.sub("o", "о", start_text)
        start_text = re.sub(r'[^\S\n]+', ' ', start_text)
        body = doc._element.body

        # Находим начальный и конечный элементы
        start_element = None
        end_element = body[-2]

        # Запись разметки исходного документа
        original_section = doc.sections[0]
        original_left_margin = original_section.left_margin  # Отступ слева
        original_right_margin = original_section.right_margin  # Отступ справа
        original_top_margin = original_section.top_margin  # Отступ сверху
        original_bottom_margin = original_section.bottom_margin  # Отступ снизу
        original_orientation = original_section.orientation  # Ориентация страницы

        # Ищем все элементы документа
        all_elements = []
        for element in body.iterchildren():
            if element.tag.endswith('p'):  # Параграф
                all_elements.append((element, Paragraph(element, doc)))
            elif element.tag.endswith('tbl'):  # Таблица
                all_elements.append((element, Table(element, doc)))

        # Ищем начальный маркер
        for element, obj in all_elements:
            if self._contains_text_forms(obj, start_text):
                start_element = element
                # break  # для первого вхождения

        if start_element is None:
            buffer = BytesIO()
            doc.save(buffer)
            byte_array = buffer.getvalue()
            buffer.close()
            return ("failed", list(byte_array))


        # Находим индексы наших элементов
        all_elements_only = [e[0] for e in all_elements]
        start_idx = all_elements_only.index(start_element)
        end_idx = all_elements_only.index(end_element)

        # Удаляем элементы до начального маркера
        for element in all_elements_only[:start_idx]:
            body.remove(element)

        doc.add_section()
        new_section = doc.sections[0]
        new_section.left_margin = original_left_margin  # Отступ слева
        new_section.right_margin = original_right_margin  # Отступ справа
        new_section.top_margin = original_top_margin  # Отступ сверху
        new_section.bottom_margin = original_bottom_margin  # Отступ снизу
        new_section.orientation = original_orientation  # Ориентация страницы
        buffer = BytesIO()
        doc.save(buffer)
        byte_array = buffer.getvalue()
        buffer.close()
        return ("processed", list(byte_array))

    def precise_trim_forms(self, start_text: str, end_text: str):
        """
        Удаляет ВСЕ элементы документа до элемента с start_text
        и ВСЕ элементы после элемента с end_text.
        Сохраняет результат в новый файл.

        :param start_text: текст начального маркера
        :param end_text: текст конечного маркера
        """
        doc = self.doc
        body = doc._element.body

        # Находим начальный и конечный элементы
        start_element = None
        end_element = None

        # Запись разметки исходного документа
        original_section = doc.sections[0]
        original_left_margin = original_section.left_margin  # Отступ слева
        original_right_margin = original_section.right_margin  # Отступ справа
        original_top_margin = original_section.top_margin  # Отступ сверху
        original_bottom_margin = original_section.bottom_margin  # Отступ снизу
        original_orientation = original_section.orientation  # Ориентация страницы

        # Ищем все элементы документа
        all_elements = []
        for element in body.iterchildren():
            if element.tag.endswith('p'):  # Параграф
                all_elements.append((element, Paragraph(element, doc)))
            elif element.tag.endswith('tbl'):  # Таблица
                all_elements.append((element, Table(element, doc)))

        # Ищем начальный маркер
        for element, obj in all_elements:
            if self._contains_text_forms(obj, start_text):
                start_element = element
                break

        if start_element is None:
            raise ValueError(f"Не удалось найти начальный маркер '{start_text}' в документе")

        # Ищем конечный маркер (только после start_element)
        start_found = False
        for element, obj in all_elements:
            if element == start_element:
                start_found = True
                continue
            if start_found and self._contains_text_forms(obj, end_text):
                end_element = element
                break

        if end_element is None:
            raise ValueError(f"Не удалось найти конечный маркер '{end_text}' в документе")

        # Находим индексы наших элементов
        all_elements_only = [e[0] for e in all_elements]
        start_idx = all_elements_only.index(start_element)
        end_idx = all_elements_only.index(end_element)

        # Удаляем элементы до начального маркера
        for element in all_elements_only[:start_idx]:
            body.remove(element)

        # Удаляем элементы после конечного маркера
        remaining_elements = list(body.iterchildren())
        end_idx_in_remaining = remaining_elements.index(end_element)

        for element in remaining_elements[end_idx_in_remaining+1:]:
            body.remove(element)

        # Применение исходной разметки документа
        doc.add_section()
        new_section = doc.sections[0]
        new_section.left_margin = original_left_margin  # Отступ слева
        new_section.right_margin = original_right_margin  # Отступ справа
        new_section.top_margin = original_top_margin  # Отступ сверху
        new_section.bottom_margin = original_bottom_margin  # Отступ снизу
        new_section.orientation = original_orientation  # Ориентация страницы
        buffer = BytesIO()
        doc.save(buffer)
        byte_array = buffer.getvalue()
        buffer.close()
        return list(byte_array)

class FormFiller:

    @staticmethod
    def _clear_text(text):
        """Отчистка текста от всего кроме букв"""
        text = text.lower()
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^a-zA-Zа-яА-ЯёЁ0-9]', '', text)
        return text

    @staticmethod
    def copy_styles(current_cell, previous_cell):
        """Функция для применения стилей с предыдущего параграфа на текущий (новый добавленный)"""
        if current_cell and previous_cell:
            current_cell.style = previous_cell.style
            source_font = previous_cell.runs[0].font
            target_font = current_cell.runs[-1].font

            # Переносим атрибуты шрифта
            target_font.name = source_font.name
            target_font.size = source_font.size
            # target_font.bold = source_font.bold
            target_font.italic = source_font.italic
            target_font.underline = source_font.underline
            target_font.color.rgb = source_font.color.rgb

    def fill_and_save(self, row):
        """Заполнение форм данными из сформированного в prepare_fill_forms словаря"""
        doc = Document(BytesIO(bytes(row.bytes)))
        data = json.loads(row.dictionary)
        # отсортируем ключи, чтобы длинные искались первыми
        pattern = r'_+'

        for key, (ptype, value) in data.items():

            if ptype == "Текст до":
                for paragraph in doc.paragraphs:
                    if self._clear_text(key) in self._clear_text(paragraph.text):  # Поиск ключа в тексте параграфа, далее поиск по ранам
                        for run_number, run in enumerate(paragraph.runs):
                            if self._clear_text(key) in self._clear_text(run.text):
                                key_index = self._clear_text(run.text).find(self._clear_text(key))
                                run_text_full = run.text
                                run_text_slice = run_text_full[key_index+len(key):]

                                if re.findall(pattern, run_text_slice):
                                    run_text_slice = re.sub(pattern, f' {value}', run_text_slice, count=1)
                                    run.text = run_text_full[:key_index+len(key)] + run_text_slice
                                else:
                                    iter_index = 1
                                    try:
                                        while not re.findall(pattern, paragraph.runs[run_number+iter_index].text):
                                            iter_index += 1
                                        run_text_next = re.sub(pattern, f' {value}', paragraph.runs[run_number+iter_index].text, count=1)
                                        paragraph.runs[run_number+iter_index].text = run_text_next
                                    except IndexError as e:
                                        continue
                            elif self._clear_text(run.text) in self._clear_text(key) and run.text.strip():
                                if re.findall(self._clear_text(paragraph.runs[run_number+1].text), self._clear_text(key)):
                                    continue
                                iter_index = 1
                                try:
                                    while not re.findall(pattern, paragraph.runs[run_number+iter_index].text):
                                        iter_index += 1
                                    run_text_next = re.sub(pattern, f' {value}', paragraph.runs[run_number+iter_index].text, count=1)
                                    paragraph.runs[run_number+iter_index].text = run_text_next
                                except IndexError as e:
                                    continue
            elif ptype == "Текст после":
                for paragraph_number, paragraph in enumerate(doc.paragraphs):
                    if self._clear_text(key) in self._clear_text(paragraph.text):
                        to_replace_paragraph = doc.paragraphs[paragraph_number-1]
                        for run in to_replace_paragraph.runs[::-1]:
                            run_text = run.text
                            if re.findall(pattern, run_text):
                                run_text = re.sub(pattern, value, run_text, count=1)
                                print(run_text)
                                run.text = run_text
                                break
            elif ptype == "Таблица":
                for table in doc.tables:
                    for row in table.rows:
                        for num, cell in enumerate(row.cells):
                            if self._clear_text(key) in self._clear_text(cell.text):
                                try:  # Для отлавливания IndexError, если не будет пустой ячейки
                                    filling_cell = row.cells[num+1]
                                    if filling_cell.text.strip():
                                        filling_cell.paragraphs[-1].runs[-1].text += "\n" + value
                                    else:
                                        filling_cell.text = str(value)
                                    self.copy_styles(filling_cell.paragraphs[-1], cell.paragraphs[-1])
                                except IndexError as e:
                                    cell.add_paragraph()
                                    cell.paragraphs[-1].text = value
                                    self.copy_styles(cell.paragraphs[-1], cell.paragraphs[0])
            elif ptype == "Гибрид":
                for table in doc.tables:
                    for row in table.rows:
                        for num, cell in enumerate(row.cells):
                            if self._clear_text(key) in self._clear_text(cell.text) and re.findall(pattern, cell.text):
                                cell.text = re.sub(pattern, f" {value}", cell.text, count = 1)
                            elif self._clear_text(key) in self._clear_text(cell.text) and not re.findall(pattern, cell.text):
                                try:
                                    next_cell = row.cells[num+1]
                                    next_cell.text = re.sub(pattern, f" {value}", next_cell.text, count=1)
                                    break
                                except IndexError as e:
                                    continue

        self.replace_last_table_with_podpis(doc)
        buffer = BytesIO()
        doc.save(buffer)
        byte_array = buffer.getvalue()
        buffer.close()
        return list(byte_array)


    def replace_last_table_with_podpis(self, doc):
        tables_with_podpis = []
        paragraphs_with_podpis = []

        # Проходим по всем таблицам в документе
        for i, table in enumerate(doc.tables):
            found = False
            for row in table.rows:
                for cell in row.cells:
                    if 'подпись' in cell.text.lower():
                        found = True
                        break
                if found:
                    break
            if found:
                tables_with_podpis.append(table)

        if not tables_with_podpis:
            to_remove = []
            pattern = r"подпись"
            for num, paragraph in enumerate(doc.paragraphs):
                matches = re.findall(pattern, paragraph.text.lower())
                if matches:
                    paragraphs_with_podpis.append((num, paragraph._element))
            if paragraphs_with_podpis:
                for num, paragraphs_el in paragraphs_with_podpis:
                    try:
                        if "___" in doc.paragraphs[num - 1].text and num - 1 not in [number_par for number_par, _ in to_remove]:
                            to_remove.append((num, doc.paragraphs[num]._element))
                            to_remove.append((num - 1, doc.paragraphs[num - 1]._element))
                        elif "___" in doc.paragraphs[num - 1].text:
                            to_remove.append((num, doc.paragraphs[num]._element))
                            to_remove.append((num + 1, doc.paragraphs[num + 1]._element))
                    except IndexError as e:
                        pass
                print(to_remove)

                target_paragraph = paragraphs_with_podpis[-1][1]
                new_table = self.create_signature_table(doc)
                par_element = target_paragraph
                par_element.addnext(new_table._tbl)
                for num, paragraph_el in to_remove:
                    paragraph_el.getparent().remove(paragraph_el)
                return None
            else:
                new_table = self.create_signature_table(doc)
                last_el = [cont for cont in doc.iter_inner_content()][-1]
                if last_el._element.tag.endswith('tbl'):
                    tbl_element = last_el._tbl
                    tbl_element.addnext(new_table._tbl)
                elif last_el._element.tag.endswith('p'):
                    par_element = last_el._element
                    par_element.addnext(new_table._tbl)
                return None

        # Выбираем последнюю таблицу
        target_table = tables_with_podpis[-1]

        # Создаём новую таблицу
        new_table = self.create_signature_table(doc)

        # Заменяем старую таблицу на новую
        tbl_element = target_table._tbl
        tbl_element.addnext(new_table._tbl)
        tbl_element.getparent().remove(tbl_element)
        return None

    def create_signature_table(self, doc):
        table = doc.add_table(rows=1, cols=2)
        table.columns[0].width = Pt(300)
        table.columns[1].width = Pt(150)

        left_cell = table.rows[0].cells[0]
        right_cell = table.rows[0].cells[1]

        # Левый столбец
        left_cell.paragraphs[0].text = "Начальник Центра торгов"
        left_cell.add_paragraph().text = "Департамента по работе"
        left_cell.add_paragraph().text = "с государственным сектором"

        for par in left_cell.paragraphs:
            par.alignment = WD_ALIGN_PARAGRAPH.LEFT
            par.paragraph_format.space_after = Pt(0)
            par.paragraph_format.space_before = Pt(0)

        # Правый столбец
        right_cell.add_paragraph()  # index 0
        right_cell.add_paragraph().text = "Баскаков Д.С."  # index 2

        for par in right_cell.paragraphs:
            par.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            par.paragraph_format.space_after = Pt(0)
            par.paragraph_format.space_before = Pt(0)

        # Применяем стиль шрифта
        for row in table.rows:
            for cell in row.cells:
                for par in cell.paragraphs:
                    for run in par.runs:
                        run.font.size = Pt(12)
                        run.font.name = 'Times New Roman'
                        run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Times New Roman')

        return table