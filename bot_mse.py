import numpy as np
# import pandas as pd
import re
import requests
import json
from bs4 import BeautifulSoup
import datetime
import os
import sqlite3
import telebot
import datetime
from background import keep_alive #импорт функции для поддержки работоспособности


def levenshtein_distance(s, t):
    """
    Calculates the Levenshtein distance between strings s and t, i.e. the
    minimum number of insertions, deletions, and substitutions required
    to transform s into t.
    """
    m, n = len(s), len(t)
    if m < n:
        # Make sure s is the longer string
        return levenshtein_distance(t, s)
    if n == 0:
        # If t is empty, s must be completely deleted
        return m
    
    # Initialize the matrix
    # previous_row stores the previous row of the matrix, which is needed for the next row
    # current_row stores the current row of the matrix, which is being filled in
    previous_row = [i for i in range(n + 1)]
    current_row = [0] * (n + 1)
    
    # Fill in the matrix row by row
    for i, c1 in enumerate(s):
        # Initialize the first element of the current row to i + 1
        # This represents the cost of deleting i + 1 characters from s to match an empty string t
        current_row[0] = i + 1
        for j, c2 in enumerate(t):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            # Choose the operation with the lowest cost
            current_row[j + 1] = min(insertions, deletions, substitutions)
        # Copy the current row to the previous row for the next iteration
        previous_row = list(current_row)
    
    # The final element of the current row contains the Levenshtein distance between s and t
    return current_row[n]
  

def find_closest_string(string_list, target_string):
    """
    Returns the string from string_list that is closest to target_string
    according to the Levenshtein distance metric.
    """
    closest_distance = float('inf')
    closest_string = None
    
    # Iterate through each string in the list
    for string in string_list:
        # Calculate the Levenshtein distance between the current string and the target string
        distance = levenshtein_distance(string, target_string)
        # If the current string is closer than the closest string found so far, update the closest string
        if distance < closest_distance:
            closest_distance = distance
            closest_string = string
    
    return closest_string


def teacher_id(cursor, surname):
    sql = f'''
    SELECT id
    FROM teachers
    WHERE last_name = ?
    '''
    cursor.execute(sql, (surname,))
    # Fetch the results and store them in a list of tuples
    data = cursor.fetchall()
    if len(data) == 0:
        return None
    else:
        return data[0][0] 
    
def surname_suggestions(cursor, surname):
    sql = f'''
      SELECT id, last_name
      FROM teachers
      WHERE LEVENSTEIN(last_name, ?) <= 3;
    '''
    cursor.execute(sql, (surname,))
    # Fetch the results and store them in a list of tuples
    data = cursor.fetchall()
    new_list = [x[1] for x in data]
    return new_list 


def find_classes_by_surname(cursor, teacher_surname, selected_day, selected_month):
    sql = '''
        SELECT classes.*
        FROM classes
        INNER JOIN teacher_class_links ON classes.id = teacher_class_links.class_id
        INNER JOIN teachers ON teacher_class_links.teacher_id = teachers.id
        WHERE ((teachers.last_name = ?) 
        AND ((classes.month = ? AND classes.day >= ? )
        OR classes.month > ?));
    '''
    cursor.execute(sql, (teacher_surname, selected_month, selected_day, selected_month))
    # Fetch the results and store them in a list of tuples
    data = cursor.fetchall()
    return data

def find_classes_by_teacher_id(cursor, teacher_id, selected_day, selected_month):
    sql = '''
        SELECT classes.*
        FROM classes
        INNER JOIN teacher_class_links ON classes.id = teacher_class_links.class_id
        WHERE ((teacher_class_links.teacher_id = ?) 
        AND ((classes.month = ? AND classes.day >= ? )
        OR classes.month > ?));
    '''
    cursor.execute(sql, (teacher_id, selected_month, selected_day, selected_month))
    # Fetch the results and store them in a list of tuples
    data = cursor.fetchall()
    return data

def full_name_by_surname(cursor, surname):
    cursor.execute('''SELECT full_name FROM teachers WHERE last_name = ? ''', (surname,))
    data = cursor.fetchall()
    return data[0][0]

def answer_text(classes):
    ans = ""
    for j in classes:
        day = str(j[2]) 
        if j[2] < 10:
            day = '0' + day
        month = str(j[3])
        if j[3] < 10:
            month = '0' + month
        time = j[4]
        info = j[5]
        string_to_add = f'*{day}.{month}, {time}*:\n\t\t\t{info}\n'
        ans += string_to_add
    return ans


if __name__ == "__main__":
    # open our database
    connection = sqlite3.connect('database.db', check_same_thread=False)
    connection.create_function("LEVENSTEIN", 2, levenshtein_distance)
    cursor = connection.cursor()
    
    # setting up our bot
    BOT_TOKEN = os.environ['BOT_TOKEN']
    bot = telebot.TeleBot(BOT_TOKEN)

    @bot.message_handler(commands=['find'])
    def handle_find_command(message):
        try:
            # Ask for the name of the teacher
            bot.send_message(message.chat.id, 'Напишите фамилию преподавателя, которого надо найти:')

             # Set a flag to indicate that we're waiting for the user's response
            bot.register_next_step_handler(message, handle_surname)
        except Exception as e:
            bot.send_message(message.chat.id, f'Произошла ошибка в работе бота: {e}')

    def handle_surname(message):
        # Extract the surname from the message text
        surname = message.text

        number = teacher_id(cursor, surname) 

        # Check if the surname is in the list
        if number is not None:
            now = datetime.datetime.now()
            day = now.day
            month = now.month
            locations = find_classes_by_teacher_id(cursor, number, day, month)
            text_locations = answer_text(locations)
            full_name = full_name_by_surname(cursor, surname)
            if len(locations) > 0:
                bot.reply_to(message, f"Преподавателя *{full_name}* можно встретить в следующие дни:\n{text_locations}",
                        parse_mode='Markdown')
            else:
                bot.reply_to(message, f"К сожалению, не удалось найти, в какие дни можно встретить преподавателя *{full_name}*.",
                        parse_mode='Markdown')
        else:
            # Create a list of similar surnames
            similar_surnames = surname_suggestions(cursor, surname)

            # If there are similar surnames, suggest them to the user
            if similar_surnames:
                suggestions = "\n\t\t".join(similar_surnames)
                no_teacher_report = "Введенная фамилия отсутствует в списке преподавателей."
                if len(similar_surnames) > 1:
                    suggestion_phrase = "Может быть, Вы имели в виду одну из следующих фамилий?"
                else:
                    suggestion_phrase = "Может быть, Вы имели в виду следующую фамилию?"
                    suggestion_phrase2 = 'Наберите команду /find еще раз, чтобы снова найти преподавателя.'
                bot.reply_to(message, f"{no_teacher_report} {suggestion_phrase}\n\t\t\t*{suggestions}*\n{suggestion_phrase2}",
                            parse_mode='Markdown')
            else:
                bot.reply_to(message, f"Введенная фамилия отсутствует в списке преподаватей.", parse_mode='Markdown')


    @bot.message_handler(commands=['help', 'start'])
    def handle_help_command(message):
        message1 = 'Нужно срочно встретиться с преподавателем, но не знаете, где его найти? Может быть, забыли его имя или отчество?'
        message2 = 'Этот бот Вам поможет! Просто введите команду /find, а затем фамилию преподавателя, которого надо найти.'
        message3 = 'В ответ Вы увидите, в какие дни и в какое время у преподавателя есть занятия.'
        message4 = 'Так Вы сможете его найти.'
        message5 = 'Обратите внимание, что бот работает в тестовом режиме, и могут случаться ошибки в его работе.'
        message6 = 'Если есть замечания и/или предложения, будем рады их услышать.'
        message7 = '\nСтраница кафедры ЭММЭ: https://mse.msu.ru/emme/'
        message8 = '\nТемы дипломных и курсовых работ на кафедре ЭММЭ можно посмотреть, набрав команду /subject'
        total_message = " ".join([message1, message2, message3, message4, message5, message6, message7])
        bot.send_message(message.chat.id, total_message, parse_mode='Markdown')

    @bot.message_handler(commands=['subject'])
    def handle_diploma_paper_command(message):
      message1 = 'Темы курсовых и дипломных работ на кафедре ЭММЭ можно посмотреть на странице'
      message2 = 'https://mse.msu.ru/tematika-kursovyh-diplomnyh-i-nauchnyh-rabot/'
      total_message = " ".join([message1, message2])
      bot.send_message(message.chat.id, total_message, parse_mode='Markdown')
  
    keep_alive()
    bot.polling()