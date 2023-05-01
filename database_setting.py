import numpy as np
import pandas as pd
import re
import requests
import json
from bs4 import BeautifulSoup
import datetime
import os
import sqlite3


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


def build_sheet_url(doc_id, sheet_id):
    return f'https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv&gid={sheet_id}'

def write_df_to_local(df, file_path):
    df.to_csv(file_path)
    
def download_from_the_site(doc_id, sheet_id, file_path=None):
    sheet_url = build_sheet_url(doc_id, sheet_id)
    df = pd.read_csv(sheet_url)
    if file_path is not None:
        write_df_to_local(df, file_path)
    return df.copy()


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




def str_month_to_numeric(month_string):
    month_dict = {"янв" : 1, "фев" : 2, "мар" : 3, "апр" : 4, "май" : 5, "июн": 6, 
               "июл" : 7, "авг" : 8, "сен" : 9, "окт" : 10, "ноя" : 11, "дек" : 12}
    month_names = list(month_dict.keys())
    return month_dict[find_closest_string(month_names, month_string)]


def deal_with_date(date_string):
    splitted = date_string.split('.')
    try:
        day = int(splitted[0])
    except ValueError:
        return -1, -1
    if len(splitted) <= 1:
        return -1, -1
    month_string = splitted[1][0:3]
    if month_string.isdigit():
        month = int(month_string)
    else:
        month = str_month_to_numeric(month_string)
    return day, month


def clear_redundant_columns(df):
    df.iloc[0][df.iloc[0].isna()] = 'время'
    mask = df.iloc[0] == df.iloc[0, 0] # choose columns to delete
    mask[0] = mask[1] = False # don't tocuch the very first column
    mask[-1] = True # clear the last column
    df.drop(df.columns[mask], axis=1, inplace=True)


def transform_cell(datum):
    if pd.isna(datum):
        return ""
    split_data = datum.split('  ')
    # strip removes leading and tailing spaces if they exist
    polished_split_data = [k.strip() for k in split_data if k != '']
    joined_cell = " ".join(polished_split_data)
    return joined_cell


def date_time(df, i, j):
    time = df.iloc[i, 0]
    if pd.isna(time):
        time = df.iloc[i-1, 0]
    date = df.iloc[0, j]
    better_date = transform_cell(date)
    day, month = deal_with_date(better_date)
    better_time = transform_cell(time)
    return (better_time, day, month)


def parse_datum(df, i, j, group=''):
    cell = df.iloc[i, j]
    if pd.isna(cell):
        return {}
    time, day, month = date_time(df, i, j)
    transformed = transform_cell(cell)
    ans = {
        "group": group,
        "month": month,
        "day": day,
        "time": time,
        "info": transformed
    }
    return ans


def parse_all_data_in_a_frame(df, group='', conn=None):
    all_classes = []
    for i in range(1, df.shape[0]):
        for j in range(1, df.shape[1]):
            u = parse_datum(df, i, j, group)
            if u != {} and (u['info'] != 'время'):
                all_classes.append(u)
    return all_classes


def change_element(list_, from_, to_, sort_=False):
    try:
        ind = list_.index(from_)
        list_[ind] = to_
        if sort_:
            list_.sort()
    except ValueError:
        print(f"Item \'{from_}\' does not exist")


if __name__ == "__main__":
    # Define connection parameters for the database
    try:
        os.remove('database.db')
        print("The old databse has been deleted.")
    except FileNotFoundError:
        print(f"The old database was not found.")
    except PermissionError:
        print("Was unable to access the database for the purposes of deleting it.")

    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()

    # Create table if it doesn't exist
    cursor.execute('''CREATE TABLE IF NOT EXISTS classes
                      (id integer PRIMARY KEY AUTOINCREMENT,
                      class_group text, month integer, day integer, time text, info text)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS teachers
                      (id integer PRIMARY KEY AUTOINCREMENT,
                      full_name, last_name, first_name, patronymic)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS teacher_class_links
                      (class_id integer, teacher_id integer,
                      FOREIGN KEY(class_id) REFERENCES classes(id),
                      FOREIGN KEY(teacher_id) REFERENCES teachers(id));''')

    print("The new databse has been created.")
    

    connection.create_function("LEVENSTEIN", 2, levenshtein_distance)

    
    # Download classes data
    with open('addresses.json', 'r') as file:
        addresses = json.load(file)

    for group in addresses.keys():
        # download the dataframe
        doc_id = addresses[group]["doc_id"]
        sheet_id = addresses[group]["sheet_id"]
        file_name = f'schedule_{group}.csv'
        print(f'Downloading schedule for {group}, doc={doc_id}, sheet={sheet_id}')
        while True:
            try:
                df = download_from_the_site(doc_id, sheet_id, file_name)
            except URLError:
                print('Ошибка соединения: заново скачиваю')
            break
        clear_redundant_columns(df)
        all_classes = parse_all_data_in_a_frame(df, group, connection)
        sql = "INSERT INTO classes (class_group, month, day, time, info) VALUES (?, ?, ?, ?, ?)"
        cursor.executemany(sql, [(x['group'], x['month'], x['day'], x['time'], x['info']) for x in all_classes])
        
     # Download teachers data
    url = 'https://mse.msu.ru/prepodavateli/'
    page = requests.get(url)
    soup = BeautifulSoup(page.text, "html.parser")
    raw_data = soup.find_all('h2', class_="entry-title fusion-post-title")
    all_teachers = []
    for data in raw_data:
        all_teachers.append(data.text)

    changes_to_make = [
        ('Андрей В. Бажанов', 'Бажанов Андрей В.'),
        ('Дайсуке Котегава', 'Котегава Дайсуке'),
        ('Либман Александр М.', 'Либман Александр М.'),
        ('Александр Мельников', 'Мельников Александр'),
        ('Дороти Дж. Розенберг', 'Розенберг Дороти Дж.'),
        ('Джозеф Й. Уграс', 'Уграс Джозеф Й.'),
        ('Деан Фантаццини', 'Фантаццини Деан'),
        ('Хаузвальд Роберт Б. Х.', 'Хаузвальд Роберт Б. Х.'),
        ('Ян Аарт Шолте', 'Шолте Ян Аарт')
    ]

    for pair in changes_to_make:
        change_element(all_teachers, pair[0], pair[1])

    all_teachers.sort()
    
    sql = "INSERT INTO teachers  (full_name, last_name, first_name, patronymic) VALUES (?, ?, ?, ?)"
    for teacher in all_teachers:
        split_name = teacher.split(' ')
        while len(split_name) < 3:
            split_name.append('')
        cursor.execute(sql, (teacher, split_name[0], split_name[1], split_name[2]))
        
    # create connections
    sql = '''
        INSERT INTO teacher_class_links (class_id, teacher_id)
        SELECT c.id, t.id
        FROM classes c
        JOIN teachers t ON c.info LIKE '%' || t.last_name || '%'
    '''
    cursor.execute(sql)

    # commit the changes to the database
    connection.commit()
    cursor.close()
    connection.close()
    print('Database update...done')