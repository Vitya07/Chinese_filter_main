import io
from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from io import BytesIO
from docx import Document as DocxDocument

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Секретный ключ для работы сессией
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///words.db'  # Путь к базе данных
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Отключаем уведомления о изменениях
db = SQLAlchemy(app)

# Модель пользователя
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    words = db.relationship('Word', backref='user', lazy=True)

# Модель документа для базы данных
class UserDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())  # Дата создания документа

    def __repr__(self):
        return f'<UserDocument {self.name}>'

# Модель слов
class Word(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('user_document.id'), nullable=False)  # Добавляем связь с документом

# Создание базы данных
with app.app_context():
    db.create_all()

# Главная страница
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('view_documents'))  # Перенаправляем на просмотр документов
    return redirect(url_for('login'))

# Страница регистрации
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            return 'Пользователь уже существует. Попробуйте другой логин.'
        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        flash('Вы успешно зарегистрированы!')  # Сообщение об успешной регистрации
        return redirect(url_for('login'))
    return render_template('register.html')

# Страница входа
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['user_id'] = user.id
            #flash('Вы успешно вошли в систему!')  # Сообщение об успешном входе
            return redirect(url_for('view_documents'))
        else:
            flash('Неверные учетные данные!')  # Сообщение об ошибке
    return render_template('login.html')

# Страница для добавления слов
# Страница для добавления слов
@app.route('/add_words/<int:document_id>', methods=['GET', 'POST'])
def add_words(document_id):
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему для добавления иероглифов.')  # Сообщение о необходимости входа
        return redirect(url_for('login'))

    # Получаем текущий документ по document_id
    current_document = UserDocument.query.get(document_id)
    if not current_document or current_document.user_id != session['user_id']:
        flash('Документ не найден или у вас нет доступа к нему.')  # Проверка доступа к документу
        return redirect(url_for('view_documents'))

    if request.method == 'POST':
        words = request.form['words']
        new_words = [word.strip() for word in words.replace(',', ' ').split()]
        user_id = session['user_id']
        
        # Добавление слов в базу данных
        for word in new_words:
            if word:  # Проверка, что слово не пустое
                new_word = Word(content=word, user_id=user_id, document_id=document_id)
                db.session.add(new_word)
        
        db.session.commit()
        #   flash('Иероглифы успешно добавлены!')  # Сообщение об успешном добавлении
        return redirect(url_for('filter_words', document_id=document_id))

    return render_template('add_words.html', document_id=document_id, document_name=current_document.name)


# Страница с отфильтрованными иероглифами
# Страница с отфильтрованными иероглифами
@app.route('/filter_words/<int:document_id>')
def filter_words(document_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    
    # Получаем слова для конкретного документа
    user_words = Word.query.filter_by(user_id=user_id, document_id=document_id).all()

    seen = set()
    unique_characters = []
    for word in user_words:
        for char in word.content:
            if char not in seen:
                seen.add(char)
                unique_characters.append(char)

    # Получаем текущий документ по document_id
    current_document = UserDocument.query.filter_by(id=document_id, user_id=user_id).first()
    document_name = current_document.name if current_document else "Без названия"

    return render_template('filtered.html', characters=unique_characters, document=current_document, document_name=document_name, document_id=document_id)


# Скачивание уникальных иероглифов в Word
# Скачивание уникальных иероглифов в Word
@app.route('/download/<int:document_id>')  # добавляем document_id в маршрут
def download(document_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Получаем текущий документ по document_id
    current_document = UserDocument.query.filter_by(id=document_id, user_id=user_id).first()
    if not current_document:
        return jsonify({'error': 'Документ не найден'}), 404

    user_words = Word.query.filter_by(user_id=user_id, document_id=document_id).all()  # Отфильтровываем слова по документу

    doc = DocxDocument()
    doc.add_heading('Уникальные иероглифы', level=1)
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = 'Иероглифы'

    seen = set()
    for word in user_words:
        for char in word.content:
            if char not in seen:
                seen.add(char)
                table.add_row().cells[0].text = char

    bio = BytesIO()
    doc.save(bio)
    bio.seek(0)

    return send_file(
        bio,
        as_attachment=True,
        download_name=f'{current_document.name}.docx',  # Используем имя документа
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )

# Скачивание выбранных иероглифов
@app.route('/download_selected/<int:document_id>', methods=['POST'])
def download_selected(document_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Необходимо войти в систему'}), 403

    # Получаем документ из базы данных
    document = UserDocument.query.get(document_id)
    if not document:
        return jsonify({'error': 'Документ не найден'}), 404

    # Получаем выбранные символы из формы
    data = request.get_json()
    characters = data.get('characters', [])

    if not characters:
        return jsonify({'error': 'Не выбраны символы'}), 400

    # Создаем новый Word-документ
    doc = DocxDocument()
    doc.add_heading('Выбранные иероглифы', level=1)
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = 'Иероглифы'

    for char in characters:
        row = table.add_row()
        row.cells[0].text = char

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'{document.name}.docx',  # Используем имя документа из базы
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )



# Очистка всех слов пользователя
@app.route('/clear_words/<int:document_id>', methods=['POST'])
def clear_words(document_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Необходимо войти в систему'}), 403

    user_id = session['user_id']
    Word.query.filter_by(user_id=user_id, document_id=document_id).delete()  # Удаляем все слова пользователя для конкретного документа
    db.session.commit()
    #flash('Все иероглифы были очищены!')  # Сообщение об успешной очистке
    return redirect(url_for('view_documents', document_id=document_id))  # Перенаправляем на страницу добавления слов с указанием document_id


# Создание документа
@app.route('/create_document', methods=['GET', 'POST'])
def create_document():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        doc_name = request.form['doc_name']
        user_id = session['user_id']

        user_words = Word.query.filter_by(user_id=user_id).all()
        unique_chars = {char for word in user_words for char in word.content}
        content = ''.join(unique_chars)

        new_document = UserDocument(name=doc_name, content=content, user_id=user_id)
        db.session.add(new_document)
        db.session.commit()

        #flash('Документ успешно создан!')  # Сообщение об успешном создании
        return redirect(url_for('view_documents'))

    return render_template('create_document.html')

# Просмотр документов
@app.route('/view_documents')
def view_documents():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    documents = UserDocument.query.filter_by(user_id=user_id).order_by(UserDocument.created_at.desc()).all()  # Сортируем по дате создания
    return render_template('view_documents.html', documents=documents)

# Выход из системы
@app.route('/logout')
def logout():
    session.pop('user_id', None)  # Удаляем user_id из сессии
    #flash('Вы вышли из системы.')  # Сообщение об успешном выходе
    return redirect(url_for('login'))  # Перенаправляем на страницу входа

# Удаление документа
@app.route('/delete_document/<int:document_id>', methods=['POST'])
def delete_document(document_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Необходимо войти в систему'}), 403

    document = UserDocument.query.get(document_id)
    if document and document.user_id == session['user_id']:
        db.session.delete(document)
        db.session.commit()
        #flash('Документ успешно удалён.')  # Сообщение об успешном удалении
    else:
        flash('Документ не найден или у вас нет доступа к нему.')  # Сообщение об ошибке
    return redirect(url_for('view_documents'))


