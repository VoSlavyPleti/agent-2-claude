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
        """Проверка наличия текста в элементе (fuzzy-matching через _clear_text)"""
        if isinstance(element, Paragraph):
            return self._clear_text(text) in self._clear_text(element.text)
        elif isinstance(element, Table):
            for row in element.rows:
                for cell in row.cells:
                    if self._clear_text(text) in self._clear_text(cell.text):
                        return True
        return False

    def _clear_text(self, text):
        """Очистка текста от всего кроме букв и цифр"""
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
    """
    Заполнение форм данными.

    Улучшения:
    - Работа на уровне run'ов для сохранения форматирования (шрифт, размер, жирность)
    - Улучшенный поиск пропусков в соседних run'ах
    - Копирование стилей при заполнении таблиц
    - Лучшая обработка ошибок с логированием
    """

    @staticmethod
    def _clear_text(text):
        """Очистка текста от всего кроме букв и цифр"""
        text = text.lower()
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^a-zA-Zа-яА-ЯёЁ0-9]', '', text)
        return text

    @staticmethod
    def copy_styles(current_cell, previous_cell):
        """Копирование стилей из предыдущего параграфа/ячейки в текущую"""
        if current_cell and previous_cell:
            try:
                current_cell.style = previous_cell.style
                if previous_cell.runs and current_cell.runs:
                    source_font = previous_cell.runs[0].font
                    target_font = current_cell.runs[-1].font

                    target_font.name = source_font.name
                    target_font.size = source_font.size
                    target_font.italic = source_font.italic
                    target_font.underline = source_font.underline
                    if source_font.color and source_font.color.rgb:
                        target_font.color.rgb = source_font.color.rgb
            except Exception as e:
                logger.warning(f"[FormFiller] Failed to copy styles: {e}")

    @staticmethod
    def _fill_run_with_value(run, value, pattern=r'_+'):
        """
        Заполнение run'а значением, заменяя подчёркивания.
        Сохраняет форматирование run'а.
        """
        run.text = re.sub(pattern, f' {value}', run.text, count=1)

    @staticmethod
    def _find_underscore_run(paragraph, start_run_index=0):
        """
        Найти первый run с подчёркиваниями начиная с указанного индекса.
        Возвращает индекс run'а или -1.
        """
        pattern = r'_+'
        for i in range(start_run_index, len(paragraph.runs)):
            if re.findall(pattern, paragraph.runs[i].text):
                return i
        return -1

    def fill_and_save(self, row):
        """
        Заполнение форм данными из сформированного в prepare_fill_forms словаря.

        Работает на уровне run'ов для максимального сохранения форматирования.
        """
        doc = Document(BytesIO(bytes(row.bytes)))
        data = json.loads(row.dictionary)
        pattern = r'_+'
        filled_count = 0
        failed_count = 0

        for key, (ptype, value) in data.items():
            try:
                if ptype == "Текст до":
                    filled = self._fill_text_before(doc, key, value, pattern)
                elif ptype == "Текст после":
                    filled = self._fill_text_after(doc, key, value, pattern)
                elif ptype == "Таблица":
                    filled = self._fill_table(doc, key, value)
                elif ptype == "Гибрид":
                    filled = self._fill_hybrid(doc, key, value, pattern)
                else:
                    filled = False

                if filled:
                    filled_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.warning(f"[FormFiller] Failed to fill '{key[:30]}' (type={ptype}): {e}")
                failed_count += 1
                continue

        logger.info(f"[FormFiller] Form filled: {filled_count} ok, {failed_count} failed, total={len(data)}")

        self.replace_last_table_with_podpis(doc)
        buffer = BytesIO()
        doc.save(buffer)
        byte_array = buffer.getvalue()
        buffer.close()
        return list(byte_array)

    def _fill_text_before(self, doc, key, value, pattern):
        """
        Тип 'Текст до': ключевое слово перед пропуском ____ в том же параграфе.
        Работает на уровне run'ов.
        """
        for paragraph in doc.paragraphs:
            if self._clear_text(key) in self._clear_text(paragraph.text):
                for run_number, run in enumerate(paragraph.runs):
                    if self._clear_text(key) in self._clear_text(run.text):
                        key_index = self._clear_text(run.text).find(self._clear_text(key))
                        run_text_full = run.text
                        run_text_slice = run_text_full[key_index + len(key):]

                        if re.findall(pattern, run_text_slice):
                            run_text_slice = re.sub(pattern, f' {value}', run_text_slice, count=1)
                            run.text = run_text_full[:key_index + len(key)] + run_text_slice
                            return True
                        else:
                            # Ищем подчёркивания в следующих run'ах
                            iter_index = 1
                            try:
                                while not re.findall(pattern, paragraph.runs[run_number + iter_index].text):
                                    iter_index += 1
                                target_run = paragraph.runs[run_number + iter_index]
                                target_run.text = re.sub(pattern, f' {value}', target_run.text, count=1)
                                return True
                            except IndexError:
                                continue
                    elif self._clear_text(run.text) in self._clear_text(key) and run.text.strip():
                        try:
                            if re.findall(self._clear_text(paragraph.runs[run_number + 1].text), self._clear_text(key)):
                                continue
                        except IndexError:
                            pass
                        iter_index = 1
                        try:
                            while not re.findall(pattern, paragraph.runs[run_number + iter_index].text):
                                iter_index += 1
                            target_run = paragraph.runs[run_number + iter_index]
                            target_run.text = re.sub(pattern, f' {value}', target_run.text, count=1)
                            return True
                        except IndexError:
                            continue
        return False

    def _fill_text_after(self, doc, key, value, pattern):
        """
        Тип 'Текст после': ключевое слово в скобках после пропуска ____.
        Ищем в предыдущем параграфе.
        """
        for paragraph_number, paragraph in enumerate(doc.paragraphs):
            if self._clear_text(key) in self._clear_text(paragraph.text):
                if paragraph_number > 0:
                    to_replace_paragraph = doc.paragraphs[paragraph_number - 1]
                    for run in to_replace_paragraph.runs[::-1]:
                        run_text = run.text
                        if re.findall(pattern, run_text):
                            run.text = re.sub(pattern, value, run_text, count=1)
                            return True
        return False

    def _fill_table(self, doc, key, value):
        """
        Тип 'Таблица': ключ в ячейке таблицы, значение в соседней (правой) ячейке.
        Работает на уровне run'ов для сохранения форматирования.
        """
        for table in doc.tables:
            for row in table.rows:
                for num, cell in enumerate(row.cells):
                    if self._clear_text(key) in self._clear_text(cell.text):
                        try:
                            filling_cell = row.cells[num + 1]
                            if filling_cell.text.strip():
                                # Ячейка не пустая — добавляем через run
                                if filling_cell.paragraphs[-1].runs:
                                    filling_cell.paragraphs[-1].runs[-1].text += "\n" + value
                                else:
                                    filling_cell.paragraphs[-1].add_run("\n" + value)
                            else:
                                # Ячейка пустая — заполняем через run для сохранения стилей
                                if filling_cell.paragraphs and filling_cell.paragraphs[0].runs:
                                    filling_cell.paragraphs[0].runs[0].text = str(value)
                                else:
                                    new_run = filling_cell.paragraphs[0].add_run(str(value))
                                    # Копируем стиль шрифта из ячейки-ключа
                                    if cell.paragraphs and cell.paragraphs[-1].runs:
                                        src_font = cell.paragraphs[-1].runs[0].font
                                        new_run.font.name = src_font.name
                                        new_run.font.size = src_font.size
                            self.copy_styles(filling_cell.paragraphs[-1], cell.paragraphs[-1])
                            return True
                        except IndexError:
                            cell.add_paragraph()
                            cell.paragraphs[-1].text = value
                            self.copy_styles(cell.paragraphs[-1], cell.paragraphs[0])
                            return True
        return False

    def _fill_hybrid(self, doc, key, value, pattern):
        """
        Тип 'Гибрид': ключ и ____ в одной ячейке таблицы.
        Работает на уровне run'ов.
        """
        for table in doc.tables:
            for row in table.rows:
                for num, cell in enumerate(row.cells):
                    if self._clear_text(key) in self._clear_text(cell.text) and re.findall(pattern, cell.text):
                        # Подчёркивания в той же ячейке что и ключ
                        # Ищем run с подчёркиваниями
                        filled = False
                        for para in cell.paragraphs:
                            for run in para.runs:
                                if re.findall(pattern, run.text):
                                    run.text = re.sub(pattern, f" {value}", run.text, count=1)
                                    filled = True
                                    break
                            if filled:
                                break
                        if not filled:
                            # Fallback: замена через cell.text (менее безопасно)
                            cell.text = re.sub(pattern, f" {value}", cell.text, count=1)
                        return True
                    elif self._clear_text(key) in self._clear_text(cell.text) and not re.findall(pattern, cell.text):
                        try:
                            next_cell = row.cells[num + 1]
                            # Ищем run с подчёркиваниями в соседней ячейке
                            filled = False
                            for para in next_cell.paragraphs:
                                for run in para.runs:
                                    if re.findall(pattern, run.text):
                                        run.text = re.sub(pattern, f" {value}", run.text, count=1)
                                        filled = True
                                        break
                                if filled:
                                    break
                            if not filled:
                                next_cell.text = re.sub(pattern, f" {value}", next_cell.text, count=1)
                            return True
                        except IndexError:
                            continue
        return False

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
                    except IndexError:
                        pass

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
