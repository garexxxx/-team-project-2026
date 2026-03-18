import mysql.connector
from mysql.connector import Error
import time
from datetime import datetime

# ========== ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ ==========
def connect_to_db():
    """Функция подключения к базе данных"""
    try:
        connection = mysql.connector.connect(
            host='localhost',
            database='internet_shop',
            user='root',
            password='180366vfn'  
        )
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"Ошибка подключения к базе данных: {e}")
        return None

# ========== ЖУРНАЛ АУДИТА ==========
def write_audit_log(user, action, details):
    """Запись действий пользователя в файл журнала"""
    try:
        with open('audit_log.txt', 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            user_info = f"{user['full_name']} ({user['role']}, ID: {user['id']})"
            f.write(f"[{timestamp}] {user_info} - {action}: {details}\n")
    except:
        pass

# ========== ФУНКЦИИ ДЛЯ ПОЛУЧЕНИЯ ДАННЫХ ==========

def get_all_products(connection):
    """Получает список всех товаров"""
    cursor = connection.cursor(dictionary=True)
    query = """
        SELECT p.id, p.name, p.price, p.stock_quantity, 
               c.name as category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        ORDER BY p.id
    """
    cursor.execute(query)
    products = cursor.fetchall()
    cursor.close()
    return products

def get_product_by_id(connection, product_id):
    """Получает товар по ID"""
    cursor = connection.cursor(dictionary=True)
    query = "SELECT * FROM products WHERE id = %s"
    cursor.execute(query, (product_id,))
    product = cursor.fetchone()
    cursor.close()
    return product

def get_categories(connection):
    """Получает список всех категорий"""
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM categories ORDER BY name")
    categories = cursor.fetchall()
    cursor.close()
    return categories

def get_all_users(connection):
    """Получает список всех пользователей (кроме гостей)"""
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, email, full_name FROM users WHERE role IN ('customer', 'manager', 'admin')")
    users = cursor.fetchall()
    cursor.close()
    return users

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ЗАКАЗАМИ ==========

def get_all_orders(connection, role='admin'):
    """Получает список всех заказов"""
    cursor = connection.cursor(dictionary=True)
    
    if role == 'admin' or role == 'manager':
        query = """
            SELECT o.id, o.order_date, o.total_amount, o.status, 
                   o.delivery_address, o.phone, u.full_name as customer_name
            FROM orders o
            JOIN users u ON o.user_id = u.id
            ORDER BY o.order_date DESC
        """
    else:
        query = """
            SELECT o.id, o.order_date, o.total_amount, o.status, 
                   o.delivery_address, o.phone
            FROM orders o
            WHERE o.user_id = %s
            ORDER BY o.order_date DESC
        """
        cursor.execute(query, (role,))
        return cursor.fetchall()
    
    cursor.execute(query)
    orders = cursor.fetchall()
    cursor.close()
    return orders

def get_order_by_id(connection, order_id):
    """Получает заказ по ID с его позициями"""
    cursor = connection.cursor(dictionary=True)
    
    # Информация о заказе
    query_order = """
        SELECT o.*, u.full_name as customer_name, u.email as customer_email
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.id = %s
    """
    cursor.execute(query_order, (order_id,))
    order = cursor.fetchone()
    
    if order:
        # Позиции заказа
        query_items = """
            SELECT oi.*, p.name as product_name
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
        """
        cursor.execute(query_items, (order_id,))
        items = cursor.fetchall()
        order['items'] = items
    
    cursor.close()
    return order

def create_order(connection, user):
    """Создание нового заказа (только для администратора)"""
    if user['role'] != 'admin':
        print("❌ У вас нет прав для создания заказов.")
        return False
    
    print("\n" + "=" * 60)
    print("СОЗДАНИЕ НОВОГО ЗАКАЗА")
    print("=" * 60)
    
    # Выбор клиента
    customers = get_all_users(connection)
    if not customers:
        print("❌ Нет доступных клиентов.")
        return False
    
    print("\nДоступные клиенты:")
    for c in customers:
        print(f"{c['id']}. {c['full_name']} ({c['email']})")
    
    try:
        user_id = int(input("\nID клиента: "))
        # Проверяем, что клиент существует
        customer_exists = any(c['id'] == user_id for c in customers)
        if not customer_exists:
            print("❌ Клиент с таким ID не существует.")
            return False
        
        delivery_address = input("Адрес доставки: ").strip()
        if not delivery_address:
            print("❌ Адрес не может быть пустым.")
            return False
        
        phone = input("Телефон: ").strip()
        if not phone:
            print("❌ Телефон не может быть пустым.")
            return False
        
        # Создаем заказ
        cursor = connection.cursor()
        query = """
            INSERT INTO orders (user_id, delivery_address, phone, status, total_amount)
            VALUES (%s, %s, %s, 'new', 0)
        """
        cursor.execute(query, (user_id, delivery_address, phone))
        order_id = cursor.lastrowid
        connection.commit()
        cursor.close()
        
        print(f"\n✅ Заказ создан! ID заказа: {order_id}")
        print("Теперь добавьте товары в заказ.")
        
        # Добавляем товары в заказ
        add_items_to_order(connection, order_id, user)
        
        # Пересчитываем итоговую сумму
        update_order_total(connection, order_id)
        
        # Запись в журнал аудита
        write_audit_log(user, "CREATE_ORDER", f"ID заказа: {order_id}, Клиент ID: {user_id}")
        
        return True
        
    except ValueError:
        print("❌ Ошибка ввода. Введите число.")
        return False
    except Error as e:
        print(f"❌ Ошибка базы данных: {e}")
        return False

def add_items_to_order(connection, order_id, user):
    """Добавление товаров в заказ"""
    products = get_all_products(connection)
    
    while True:
        print("\n" + "-" * 40)
        print("ДОСТУПНЫЕ ТОВАРЫ:")
        for p in products:
            print(f"{p['id']}. {p['name']} - {p['price']} руб. (в наличии: {p['stock_quantity']})")
        print("-" * 40)
        
        try:
            prod_id = input("\nВведите ID товара (или 'стоп' для завершения): ")
            if prod_id.lower() == 'стоп':
                break
            
            prod_id = int(prod_id)
            
            # Проверяем, что товар существует
            product = next((p for p in products if p['id'] == prod_id), None)
            if not product:
                print("❌ Товар не найден.")
                continue
            
            quantity = int(input(f"Количество (макс. {product['stock_quantity']}): "))
            if quantity <= 0:
                print("❌ Количество должно быть больше 0.")
                continue
            if quantity > product['stock_quantity']:
                print(f"❌ Недостаточно товара. Доступно: {product['stock_quantity']}")
                continue
            
            # Добавляем в order_items
            cursor = connection.cursor()
            query = """
                INSERT INTO order_items (order_id, product_id, quantity, price_at_moment)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query, (order_id, prod_id, quantity, product['price']))
            connection.commit()
            cursor.close()
            
            print(f"✅ Товар добавлен в заказ.")
            
        except ValueError:
            print("❌ Ошибка ввода. Введите число.")
        except Error as e:
            print(f"❌ Ошибка базы данных: {e}")

def update_order_total(connection, order_id):
    """Пересчитывает итоговую сумму заказа"""
    cursor = connection.cursor()
    
    # Суммируем стоимость всех позиций
    query = """
        UPDATE orders o
        SET total_amount = (
            SELECT SUM(quantity * price_at_moment)
            FROM order_items
            WHERE order_id = %s
        )
        WHERE o.id = %s
    """
    cursor.execute(query, (order_id, order_id))
    connection.commit()
    cursor.close()

def view_orders(connection, user):
    """Просмотр заказов"""
    if user['role'] not in ['admin', 'manager']:
        print("❌ У вас нет прав для просмотра всех заказов.")
        return
    
    orders = get_all_orders(connection, user['role'])
    
    if not orders:
        print("\n📭 Заказы не найдены.")
        return
    
    print("\n" + "=" * 100)
    print(f"{'ID':<5} {'ДАТА':<20} {'КЛИЕНТ':<20} {'СУММА':<12} {'СТАТУС':<15} {'ТЕЛЕФОН':<15}")
    print("=" * 100)
    
    for o in orders:
        date = o['order_date'].strftime("%d.%m.%Y %H:%M") if o['order_date'] else ""
        print(f"{o['id']:<5} {date:<20} {o['customer_name'][:18]:<20} "
              f"{o['total_amount']:<12.2f} {o['status']:<15} {o['phone'][:14]:<15}")
    
    print("=" * 100)

def view_order_details(connection, user):
    """Просмотр деталей заказа"""
    try:
        order_id = int(input("\nВведите ID заказа: "))
    except ValueError:
        print("❌ Введите число")
        return
    
    order = get_order_by_id(connection, order_id)
    
    if not order:
        print(f"❌ Заказ с ID {order_id} не найден.")
        return
    
    print("\n" + "=" * 60)
    print(f"ДЕТАЛИ ЗАКАЗА №{order_id}")
    print("=" * 60)
    print(f"Клиент: {order['customer_name']} ({order['customer_email']})")
    print(f"Дата: {order['order_date']}")
    print(f"Адрес: {order['delivery_address']}")
    print(f"Телефон: {order['phone']}")
    print(f"Статус: {order['status']}")
    print(f"Общая сумма: {order['total_amount']} руб.")
    print("-" * 60)
    print("СОСТАВ ЗАКАЗА:")
    print(f"{'Товар':<40} {'Кол-во':<10} {'Цена':<12} {'Сумма':<12}")
    print("-" * 60)
    
    for item in order['items']:
        sum_item = item['quantity'] * item['price_at_moment']
        print(f"{item['product_name'][:38]:<40} {item['quantity']:<10} "
              f"{item['price_at_moment']:<12.2f} {sum_item:<12.2f}")
    
    print("=" * 60)

def update_order_status(connection, user):
    """Изменение статуса заказа"""
    if user['role'] not in ['admin', 'manager']:
        print("❌ У вас нет прав для изменения статуса.")
        return
    
    try:
        order_id = int(input("\nВведите ID заказа: "))
    except ValueError:
        print("❌ Введите число")
        return
    
    order = get_order_by_id(connection, order_id)
    if not order:
        print(f"❌ Заказ с ID {order_id} не найден.")
        return
    
    print(f"\nТекущий статус заказа: {order['status']}")
    print("\nДоступные статусы:")
    statuses = ['new', 'processing', 'shipped', 'delivered', 'cancelled']
    for i, s in enumerate(statuses, 1):
        print(f"{i}. {s}")
    
    try:
        choice = int(input("Выберите новый статус (1-5): "))
        if choice < 1 or choice > 5:
            print("❌ Неверный выбор.")
            return
        
        new_status = statuses[choice - 1]
        
        # Проверка: нельзя изменить статус с delivered или cancelled
        if order['status'] in ['delivered', 'cancelled'] and user['role'] != 'admin':
            print("❌ Только администратор может изменять статус доставленных или отмененных заказов.")
            return
        
        cursor = connection.cursor()
        query = "UPDATE orders SET status = %s WHERE id = %s"
        cursor.execute(query, (new_status, order_id))
        connection.commit()
        cursor.close()
        
        print(f"✅ Статус заказа изменен на '{new_status}'")
        
        # Запись в журнал аудита
        write_audit_log(user, "CHANGE_ORDER_STATUS", 
                       f"Заказ ID: {order_id}, Статус: {order['status']} -> {new_status}")
        
    except ValueError:
        print("❌ Введите число")

def delete_order(connection, user):
    """Удаление заказа (только для администратора)"""
    if user['role'] != 'admin':
        print("❌ Только администратор может удалять заказы.")
        return
    
    try:
        order_id = int(input("\nВведите ID заказа для удаления: "))
    except ValueError:
        print("❌ Введите число")
        return
    
    order = get_order_by_id(connection, order_id)
    if not order:
        print(f"❌ Заказ с ID {order_id} не найден.")
        return
    
    # Проверка: нельзя удалить выполненные заказы
    if order['status'] in ['delivered', 'shipped']:
        print("❌ Нельзя удалить заказ со статусом 'delivered' или 'shipped'.")
        return
    
    print(f"\nЗаказ №{order_id} от {order['customer_name']}")
    print(f"Сумма: {order['total_amount']} руб.")
    print(f"Статус: {order['status']}")
    
    confirm = input("\nДля подтверждения удаления введите 'УДАЛИТЬ': ")
    if confirm != "УДАЛИТЬ":
        print("Операция отменена.")
        return
    
    try:
        cursor = connection.cursor()
        
        # Сначала удаляем связанные записи из order_items
        cursor.execute("DELETE FROM order_items WHERE order_id = %s", (order_id,))
        # Затем удаляем сам заказ
        cursor.execute("DELETE FROM orders WHERE id = %s", (order_id,))
        connection.commit()
        cursor.close()
        
        print(f"✅ Заказ №{order_id} успешно удален.")
        
        # Запись в журнал аудита
        write_audit_log(user, "DELETE_ORDER", f"Заказ ID: {order_id}, Сумма: {order['total_amount']}")
        
    except Error as e:
        print(f"❌ Ошибка при удалении: {e}")
        connection.rollback()

# ========== ФУНКЦИИ ДЛЯ ТОВАРОВ (CRUD) ==========

def add_product(connection, user):
    """Добавление нового товара (только для администратора)"""
    if user['role'] != 'admin':
        print("❌ У вас нет прав для добавления товаров.")
        return False
    
    print("\n" + "=" * 60)
    print("ДОБАВЛЕНИЕ НОВОГО ТОВАРА")
    print("=" * 60)
    
    categories = get_categories(connection)
    if not categories:
        print("❌ Нет доступных категорий.")
        return False
    
    print("\nДоступные категории:")
    for cat in categories:
        print(f"{cat['id']}. {cat['name']}")
    
    try:
        category_id = int(input("\nID категории: "))
        category_exists = any(cat['id'] == category_id for cat in categories)
        if not category_exists:
            print("❌ Категория не существует.")
            return False
        
        name = input("Название товара: ").strip()
        if not name:
            print("❌ Название не может быть пустым.")
            return False
        
        price = float(input("Цена: "))
        if price <= 0:
            print("❌ Цена должна быть больше 0.")
            return False
        
        stock = int(input("Количество на складе: "))
        if stock < 0:
            print("❌ Количество не может быть отрицательным.")
            return False
        
        description = input("Описание (можно оставить пустым): ").strip()
        
        cursor = connection.cursor()
        query = """
            INSERT INTO products (category_id, name, price, stock_quantity, description)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(query, (category_id, name, price, stock, description))
        connection.commit()
        product_id = cursor.lastrowid
        cursor.close()
        
        print(f"\n✅ Товар успешно добавлен! ID товара: {product_id}")
        write_audit_log(user, "ADD_PRODUCT", f"ID: {product_id}, Название: {name}")
        
        return True
        
    except ValueError:
        print("❌ Ошибка ввода.")
        return False

def edit_product(connection, user):
    """Редактирование товара"""
    if user['role'] != 'admin':
        print("❌ У вас нет прав для редактирования товаров.")
        return False
    
    try:
        product_id = int(input("\nВведите ID товара для редактирования: "))
    except ValueError:
        print("❌ Введите число")
        return False
    
    product = get_product_by_id(connection, product_id)
    if not product:
        print(f"❌ Товар с ID {product_id} не найден.")
        return False
    
    print("\n" + "=" * 60)
    print(f"РЕДАКТИРОВАНИЕ ТОВАРА ID: {product_id}")
    print("=" * 60)
    print(f"Текущие данные:")
    print(f"Название: {product['name']}")
    print(f"Цена: {product['price']}")
    print(f"Количество: {product['stock_quantity']}")
    print(f"Описание: {product['description']}")
    print("-" * 60)
    print("Оставьте поле пустым, чтобы оставить текущее значение")
    
    categories = get_categories(connection)
    
    try:
        cat_input = input(f"ID категории (текущий: {product['category_id']}): ").strip()
        category_id = int(cat_input) if cat_input else product['category_id']
        
        name = input(f"Название (текущее: {product['name']}): ").strip()
        if not name:
            name = product['name']
        
        price_input = input(f"Цена (текущая: {product['price']}): ").strip()
        price = float(price_input) if price_input else product['price']
        
        stock_input = input(f"Количество (текущее: {product['stock_quantity']}): ").strip()
        stock = int(stock_input) if stock_input else product['stock_quantity']
        
        desc_input = input(f"Описание (текущее: {product['description']}): ").strip()
        description = desc_input if desc_input else product['description']
        
        cursor = connection.cursor()
        query = """
            UPDATE products 
            SET category_id = %s, name = %s, price = %s, stock_quantity = %s, description = %s
            WHERE id = %s
        """
        cursor.execute(query, (category_id, name, price, stock, description, product_id))
        connection.commit()
        cursor.close()
        
        print(f"\n✅ Товар ID {product_id} успешно обновлен!")
        write_audit_log(user, "EDIT_PRODUCT", f"ID: {product_id}, Новое название: {name}")
        
        return True
        
    except ValueError:
        print("❌ Ошибка ввода.")
        return False

def delete_product(connection, user):
    """Удаление товара"""
    if user['role'] != 'admin':
        print("❌ У вас нет прав для удаления товаров.")
        return False
    
    try:
        product_id = int(input("\nВведите ID товара для удаления: "))
    except ValueError:
        print("❌ Введите число")
        return False
    
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM order_items WHERE product_id = %s", (product_id,))
    result = cursor.fetchone()
    
    if result[0] > 0:
        print(f"\n⚠ Внимание! Этот товар есть в {result[0]} заказах.")
        confirm = input("Удаление товара удалит его из всех заказов. Продолжить? (да/нет): ")
        if confirm.lower() != 'да':
            print("Операция отменена.")
            cursor.close()
            return False
    
    cursor.execute("SELECT name FROM products WHERE id = %s", (product_id,))
    product = cursor.fetchone()
    if not product:
        print(f"❌ Товар с ID {product_id} не найден.")
        cursor.close()
        return False
    
    product_name = product[0]
    
    print(f"\nВы собираетесь удалить товар: {product_name}")
    confirm = input("Для подтверждения введите 'УДАЛИТЬ': ")
    
    if confirm != "УДАЛИТЬ":
        print("Операция отменена.")
        cursor.close()
        return False
    
    try:
        cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
        connection.commit()
        print(f"\n✅ Товар ID {product_id} успешно удален!")
        write_audit_log(user, "DELETE_PRODUCT", f"ID: {product_id}, Название: {product_name}")
        
    except Error as e:
        print(f"❌ Ошибка при удалении: {e}")
        connection.rollback()
        return False
    finally:
        cursor.close()
    
    return True

def view_audit_log(user):
    """Просмотр журнала аудита"""
    if user['role'] != 'admin':
        print("❌ У вас нет прав для просмотра журнала.")
        return
    
    try:
        with open('audit_log.txt', 'r', encoding='utf-8') as f:
            logs = f.readlines()
        
        print("\n" + "=" * 80)
        print("ЖУРНАЛ АУДИТА (последние 20 записей)")
        print("=" * 80)
        
        if not logs:
            print("Журнал пуст.")
        else:
            for log in logs[-20:]:
                print(log.strip())
        
        print("=" * 80)
        
    except FileNotFoundError:
        print("Журнал аудита еще не создан.")

# ========== МЕНЮ КАТАЛОГА И ЗАКАЗОВ ==========

def catalog_menu(connection, user):
    """Меню каталога товаров"""
    role = user['role']
    
    while True:
        print("\n" + "=" * 60)
        print(f"КАТАЛОГ ТОВАРОВ - {user['full_name']} ({role})")
        print("=" * 60)
        print("1. Показать все товары")
        print("2. Поиск товаров")
        print("3. Фильтр по категории")
        print("4. Детальная информация о товаре")
        
        if role == 'admin':
            print("\n--- УПРАВЛЕНИЕ ТОВАРАМИ ---")
            print("5. ➕ Добавить новый товар")
            print("6. ✏️ Редактировать товар")
            print("7. ❌ Удалить товар")
        
        print("\n0. Вернуться в главное меню")
        print("-" * 60)
        
        choice = input("Выберите действие: ")
        
        if choice == '1':
            products = get_all_products(connection)
            if products:
                print("\n" + "=" * 90)
                print(f"{'ID':<5} {'НАЗВАНИЕ':<30} {'КАТЕГОРИЯ':<20} {'ЦЕНА':<10} {'В НАЛИЧИИ':<10}")
                print("=" * 90)
                for p in products:
                    stock = "Да" if p['stock_quantity'] > 0 else "Нет"
                    print(f"{p['id']:<5} {p['name'][:28]:<30} {p['category_name'][:18]:<20} "
                          f"{p['price']:<10.2f} {stock:<10}")
                print("=" * 90)
            else:
                print("\n📭 Товары не найдены.")
        
        elif choice == '2':
            search = input("Введите текст для поиска: ").lower()
            products = get_all_products(connection)
            filtered = [p for p in products if search in p['name'].lower()]
            if filtered:
                print("\n" + "=" * 90)
                print(f"{'ID':<5} {'НАЗВАНИЕ':<30} {'КАТЕГОРИЯ':<20} {'ЦЕНА':<10} {'В НАЛИЧИИ':<10}")
                print("=" * 90)
                for p in filtered:
                    stock = "Да" if p['stock_quantity'] > 0 else "Нет"
                    print(f"{p['id']:<5} {p['name'][:28]:<30} {p['category_name'][:18]:<20} "
                          f"{p['price']:<10.2f} {stock:<10}")
                print("=" * 90)
            else:
                print("Ничего не найдено.")
        
        elif choice == '3':
            categories = get_categories(connection)
            if categories:
                print("\nКатегории:")
                for cat in categories:
                    print(f"{cat['id']}. {cat['name']}")
                try:
                    cat_id = int(input("Введите ID категории: "))
                    products = get_all_products(connection)
                    filtered = [p for p in products if p.get('category_id') == cat_id]
                    if filtered:
                        print("\n" + "=" * 90)
                        print(f"{'ID':<5} {'НАЗВАНИЕ':<30} {'КАТЕГОРИЯ':<20} {'ЦЕНА':<10} {'В НАЛИЧИИ':<10}")
                        print("=" * 90)
                        for p in filtered:
                            stock = "Да" if p['stock_quantity'] > 0 else "Нет"
                            print(f"{p['id']:<5} {p['name'][:28]:<30} {p['category_name'][:18]:<20} "
                                  f"{p['price']:<10.2f} {stock:<10}")
                        print("=" * 90)
                    else:
                        print("В этой категории нет товаров.")
                except ValueError:
                    print("❌ Введите число")
            else:
                print("❌ Нет категорий")
        
        elif choice == '4':
            try:
                prod_id = int(input("Введите ID товара: "))
                product = get_product_by_id(connection, prod_id)
                if product:
                    print("\n" + "=" * 60)
                    print(f"ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О ТОВАРЕ")
                    print("=" * 60)
                    print(f"ID: {product['id']}")
                    print(f"Название: {product['name']}")
                    # Получаем название категории
                    cursor = connection.cursor()
                    cursor.execute("SELECT name FROM categories WHERE id = %s", (product['category_id'],))
                    cat = cursor.fetchone()
                    cursor.close()
                    print(f"Категория: {cat[0] if cat else 'Без категории'}")
                    print(f"Цена: {product['price']} руб.")
                    print(f"В наличии: {product['stock_quantity']} шт.")
                    print(f"Описание: {product['description'] or 'Нет описания'}")
                    print("=" * 60)
                else:
                    print("❌ Товар не найден.")
            except ValueError:
                print("❌ Введите число")
        
        elif choice == '5' and role == 'admin':
            add_product(connection, user)
        
        elif choice == '6' and role == 'admin':
            edit_product(connection, user)
        
        elif choice == '7' and role == 'admin':
            delete_product(connection, user)
        
        elif choice == '0':
            break
        
        else:
            print("❌ Неверный выбор.")
        
        input("\nНажмите Enter, чтобы продолжить...")

def orders_menu(connection, user):
    """Меню управления заказами"""
    role = user['role']
    
    if role not in ['admin', 'manager']:
        print("❌ У вас нет доступа к управлению заказами.")
        input("Нажмите Enter, чтобы продолжить...")
        return
    
    while True:
        print("\n" + "=" * 60)
        print(f"УПРАВЛЕНИЕ ЗАКАЗАМИ - {user['full_name']} ({role})")
        print("=" * 60)
        print("1. Просмотреть все заказы")
        print("2. Детали заказа")
        print("3. Изменить статус заказа")
        
        if role == 'admin':
            print("\n--- ПОЛНЫЙ ДОСТУП (АДМИН) ---")
            print("4. ➕ Создать новый заказ")
            print("5. ❌ Удалить заказ")
        
        print("\n0. Вернуться в главное меню")
        print("-" * 60)
        
        choice = input("Выберите действие: ")
        
        if choice == '1':
            view_orders(connection, user)
        
        elif choice == '2':
            view_order_details(connection, user)
        
        elif choice == '3':
            update_order_status(connection, user)
        
        elif choice == '4' and role == 'admin':
            create_order(connection, user)
        
        elif choice == '5' and role == 'admin':
            delete_order(connection, user)
        
        elif choice == '0':
            break
        
        else:
            print("❌ Неверный выбор.")
        
        input("\nНажмите Enter, чтобы продолжить...")

# ========== ФУНКЦИИ АВТОРИЗАЦИИ ==========

def login_user(connection, login, password):
    """Проверяет логин и пароль, возвращает пользователя"""
    cursor = connection.cursor(dictionary=True)
    query = "SELECT id, email, full_name, role FROM users WHERE email = %s AND password = %s"
    cursor.execute(query, (login, password))
    user = cursor.fetchone()
    cursor.close()
    return user

def show_login_window():
    """Показывает форму входа"""
    print("=" * 40)
    print("     ДОБРО ПОЖАЛОВАТЬ В ИНТЕРНЕТ-МАГАЗИН")
    print("=" * 40)
    print("1. Войти")
    print("2. Продолжить как гость")
    print("3. Выход")
    print("-" * 40)
    return input("Выберите действие (1-3): ")

def guest_mode():
    """Режим гостя"""
    print("\n" + "=" * 40)
    print("     ГОСТЕВОЙ РЕЖИМ")
    print("=" * 40)
    return {'id': 0, 'role': 'guest', 'full_name': 'Гость', 'email': ''}

# ========== ГЛАВНОЕ МЕНЮ ПОСЛЕ ВХОДА ==========

def main_menu(connection, user):
    """Главное меню после авторизации"""
    while True:
        print("\n" + "=" * 60)
        print(f"ГЛАВНОЕ МЕНЮ - {user['full_name']} ({user['role']})")
        print("=" * 60)
        print("1. 📦 Каталог товаров")
        
        if user['role'] in ['admin', 'manager']:
            print("2. 📋 Управление заказами")
        
        if user['role'] == 'admin':
            print("3. 📊 Журнал аудита")
        
        print("\n0. Выйти из системы")
        print("-" * 60)
        
        choice = input("Выберите действие: ")
        
        if choice == '1':
            catalog_menu(connection, user)
        
        elif choice == '2' and user['role'] in ['admin', 'manager']:
            orders_menu(connection, user)
        
        elif choice == '3' and user['role'] == 'admin':
            view_audit_log(user)
            input("\nНажмите Enter, чтобы продолжить...")
        
        elif choice == '0':
            print("\n🚪 Выход из системы...")
            if user['role'] != 'guest':
                write_audit_log(user, "LOGOUT", "Выход из системы")
            break
        
        else:
            print("❌ Неверный выбор.")

# ========== ОСНОВНАЯ ПРОГРАММА ==========

def main():
    connection = connect_to_db()
    if not connection:
        print("Не удалось подключиться к базе данных.")
        return
    
    failed_attempts = 0
    max_attempts = 3
    current_user = None
    
    while True:
        if not current_user:
            choice = show_login_window()
            
            if choice == '1':
                print("\n--- ВХОД В СИСТЕМУ ---")
                login = input("Email: ")
                password = input("Пароль: ")
                
                user = login_user(connection, login, password)
                
                if user:
                    print(f"\n✓ Успешный вход! Ваша роль: {user['role']}")
                    failed_attempts = 0
                    current_user = user
                    write_audit_log(user, "LOGIN", "Успешный вход в систему")
                else:
                    failed_attempts += 1
                    print(f"\n✗ Неверный email или пароль. Осталось попыток: {max_attempts - failed_attempts}")
                    
                    if failed_attempts >= max_attempts:
                        print("\n⚠ Слишком много неудачных попыток. Подождите 10 секунд...")
                        time.sleep(10)
                        failed_attempts = 0
            
            elif choice == '2':
                current_user = guest_mode()
            
            elif choice == '3':
                print("\nДо свидания!")
                break
            
            else:
                print("\n✗ Неверный выбор.")
        
        if current_user:
            main_menu(connection, current_user)
            current_user = None
        
        print("\n" + "-" * 40)
    
    if connection.is_connected():
        connection.close()

if __name__ == "__main__":
    main()