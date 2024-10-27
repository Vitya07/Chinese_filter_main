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


class Glyph(db.Model):
    __tablename__ = 'glyph'
    id = db.Column(db.Integer, primary_key=True)
    char = db.Column(db.String, nullable=False)
    order = db.Column(db.Integer, default=0)
    document_id = db.Column(db.Integer, db.ForeignKey('user_document.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('char', 'document_id', 'user_id', name='unique_glyph_constraint'),
    )

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

    words = db.relationship('Word', backref='user', lazy=True)
    glyphs = db.relationship('Glyph', backref='user', lazy=True)

class UserDocument(db.Model):
    __tablename__ = 'user_document'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    words = db.relationship('Word', backref='document', lazy=True)

class Word(db.Model):
    __tablename__ = 'word'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('user_document.id'), nullable=False)



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
            return redirect(url_for('view_documents'))
        else:
            flash('Неверные учетные данные!')  # Сообщение об ошибке
    return render_template('login.html')

# Страница для добавления слов
@app.route('/add_words/<int:document_id>', methods=['GET', 'POST'])
def add_words(document_id):
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему для добавления иероглифов.')
        return redirect(url_for('login'))

    current_document = UserDocument.query.get(document_id)
    if not current_document or current_document.user_id != session['user_id']:
        flash('Документ не найден или у вас нет доступа к нему.')
        return redirect(url_for('view_documents'))

    if request.method == 'POST':
        words = request.form['words']
        new_words = [word.strip() for word in words.replace(',', ' ').split() if word]
        user_id = session['user_id']

        unique_glyphs = set()  # Множество для хранения уникальных иероглифов

        for word in new_words:
            new_word = Word(content=word, user_id=user_id, document_id=document_id)
            db.session.add(new_word)
            unique_glyphs.update(word)  # Собираем уникальные иероглифы

        # Добавляем уникальные иероглифы в базу данных
        for char in unique_glyphs:
            # Проверка существования иероглифа
            glyph = Glyph.query.filter_by(char=char, document_id=document_id, user_id=user_id).first()
            if not glyph:
                db.session.add(Glyph(char=char, document_id=document_id, user_id=user_id))

        db.session.commit()  # Сохраняем изменения в базе данных
        flash('Слова и уникальные иероглифы успешно добавлены.')
        return redirect(url_for('filter_words', document_id=document_id))

    return render_template('add_words.html', document_id=document_id, document_name=current_document.name)

@app.route('/filter_words/<int:document_id>')
def filter_words(document_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    
    # Получаем слова для конкретного документа
    user_words = Word.query.filter_by(user_id=user_id, document_id=document_id).all()

    unique_characters = set()  # Используем множество для уникальных иероглифов
    for word in user_words:
        unique_characters.update(word.content)  # Обновляем множество уникальных иероглифов

    # Получаем текущий документ
    current_document = UserDocument.query.get(document_id)
    document_name = current_document.name if current_document else "Без названия"

    return render_template('filtered.html', characters=list(unique_characters), document=current_document, document_name=document_name, document_id=document_id)

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

@app.route('/clear_words/<int:document_id>', methods=['POST'])
def clear_words(document_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Необходимо войти в систему'}), 403

    user_id = session['user_id']
    try:
        # Удаляем все слова пользователя для конкретного документа
        Word.query.filter_by(user_id=user_id, document_id=document_id).delete()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Все слова успешно очищены.'})
    except Exception as e:
        db.session.rollback()  # Откат транзакции в случае ошибки
        return jsonify({'error': f'Ошибка при удалении: {str(e)}'}), 500

# Создание документа
@app.route('/create_document', methods=['GET', 'POST'])
def create_document():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        doc_name = request.form['doc_name'].strip()
        user_id = session['user_id']

        # Проверка на пустое имя документа
        if not doc_name:
            flash('Имя документа не может быть пустым.')  # Сообщение об ошибке
            return redirect(url_for('create_document'))

        # Создаем новый документ
        new_document = UserDocument(name=doc_name, content='', user_id=user_id)
        db.session.add(new_document)
        db.session.commit()  # Сохраняем изменения в базе данных

        # Перенаправляем на страницу добавления слов
        return redirect(url_for('add_words', document_id=new_document.id))

    return render_template('create_document.html')

# Просмотр документов
@app.route('/view_documents')
def view_documents():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    documents = UserDocument.query.filter_by(user_id=user_id).order_by(UserDocument.created_at.desc()).all()  # Сортируем по дате создания

    # Собираем уникальные иероглифы для каждого документа
    unique_characters = {}
    for document in documents:
        user_words = Word.query.filter_by(document_id=document.id, user_id=user_id).all()
        seen = set()
        unique_characters[document.id] = []
        for word in user_words:
            for char in word.content:
                if char not in seen:
                    seen.add(char)
                    unique_characters[document.id].append(char)

    return render_template('view_documents.html', documents=documents, unique_characters=unique_characters)

# Выход из системы
@app.route('/logout')
def logout():
    session.pop('user_id', None)  # Удаляем user_id из сессии
    return redirect(url_for('login'))  # Перенаправляем на страницу входа

# Удаление документа
@app.route('/delete_document/<int:document_id>', methods=['POST'])
def delete_document(document_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Необходимо войти в систему'}), 403

    document = UserDocument.query.get(document_id)
    if document and document.user_id == session['user_id']:
        try:
            # Удаляем все слова и иероглифы, связанные с документом
            Word.query.filter_by(document_id=document.id).delete()
            Glyph.query.filter_by(document_id=document.id).delete()

            # Удаляем сам документ
            db.session.delete(document)
            db.session.commit()
            flash('Документ успешно удалён!')
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при удалении: {str(e)}')
    else:
        flash('Документ не найден или у вас нет доступа.')

    return redirect(url_for('view_documents'))


@app.route('/rename_document/<int:document_id>', methods=['POST'])
def rename_document(document_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Необходимо войти в систему'}), 403

    document = UserDocument.query.get(document_id)
    if document and document.user_id == session['user_id']:
        new_name = request.form['new_name'].strip()
        if new_name and not UserDocument.query.filter_by(name=new_name, user_id=session['user_id']).first():
            document.name = new_name
            db.session.commit()
            flash('Документ успешно переименован!')
        else:
            flash('Имя документа уже существует или недопустимо.')
    else:
        flash('Документ не найден или у вас нет доступа.')

    return redirect(url_for('view_documents'))



@app.route('/edit_document/<int:document_id>', methods=['GET', 'POST'])
def edit_document(document_id):
    document = UserDocument.query.get_or_404(document_id)
    
    if request.method == 'POST':
        new_name = request.form['new_name'].strip()
        order = request.form.get('order', '').split(',')

        if not new_name:
            flash('Имя документа не может быть пустым.')
            return redirect(url_for('edit_document', document_id=document_id))

        document.name = new_name  # Обновляем имя документа

        # Обновляем порядок существующих иероглифов
        for index, char in enumerate(order):
            glyph = Glyph.query.filter_by(char=char, document_id=document.id).first()
            if glyph:
                glyph.order = index  # Устанавливаем новый порядок

        db.session.commit()
        flash('Документ успешно обновлён!')
        return redirect(url_for('view_documents'))

    # Получаем иероглифы для текущего документа
    characters = Glyph.query.filter_by(document_id=document.id).order_by(Glyph.order).all()

    return render_template('edit_document.html', document=document, characters=characters)


@app.route('/delete_glyph/<int:glyph_id>', methods=['POST'])
def delete_glyph(glyph_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Необходимо войти в систему'}), 403

    glyph = Glyph.query.get(glyph_id)
    if glyph and glyph.user_id == session['user_id']:
        db.session.delete(glyph)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Иероглиф успешно удалён.'})
    else:
        return jsonify({'error': 'Иероглиф не найден или у вас нет доступа.'}), 404

@app.route('/delete_selected/<int:document_id>', methods=['POST'])
def delete_selected(document_id):
    document = UserDocument.query.get_or_404(document_id)
    data = request.get_json()
    
    if not data or 'ids' not in data:
        return jsonify({'success': False, 'error': 'Не указаны идентификаторы иероглифов для удаления.'})

    ids_to_delete = data['ids']
    
    # Удаляем иероглифы по идентификаторам
    Glyph.query.filter(Glyph.id.in_(ids_to_delete), Glyph.document_id == document.id).delete(synchronize_session=False)
    
    db.session.commit()

    # Получаем оставшиеся иероглифы для обновления
    remaining_glyphs = Glyph.query.filter_by(document_id=document.id).all()
    remaining_chars = [glyph.char for glyph in remaining_glyphs]

    return jsonify({
        'success': True,
        'remaining_chars': remaining_chars  # Отправляем оставшиеся иероглифы обратно
    })

@app.route('/clear_glyphs/<int:document_id>', methods=['POST'])
def clear_glyphs(document_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Необходимо войти в систему'}), 403

    user_id = session['user_id']
    deleted_count = Glyph.query.filter_by(user_id=user_id, document_id=document_id).delete()
    db.session.commit()  # Сохраняем изменения в базе данных
    
    flash('Все иероглифы успешно очищены.')  # Сообщение об успешной очистке
    return redirect(url_for('filter_words', document_id=document_id))
