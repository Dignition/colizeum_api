import logging
from logging.config import fileConfig

from flask import current_app

from alembic import context
from sqlalchemy import create_engine

# Объект конфигурации Alembic (config):
# позволяет читать параметры из файла alembic.ini.
config = context.config

# Инициализация логирования по настройкам alembic.ini.
# По сути эта строка настраивает логгеры для вывода Alembic.
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')


def get_engine():
    try:
        # Для Flask-SQLAlchemy < 3 и Alchemical
        return current_app.extensions['migrate'].db.get_engine()
    except (TypeError, AttributeError):
        # Для Flask-SQLAlchemy >= 3
        return current_app.extensions['migrate'].db.engine


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace(
            '%', '%%')
    except AttributeError:
        return str(get_engine().url).replace('%', '%%')

# Если бы мы не использовали Flask-Migrate, здесь можно было бы
# указать MetaData ваших моделей для режима автогенерации.
# Пример:
#   from myapp import mymodel
#   target_metadata = mymodel.Base.metadata
config.set_main_option('sqlalchemy.url', get_engine_url())
target_db = current_app.extensions['migrate'].db

# Другие значения из alembic.ini можно получать так, если потребуется:
#   my_important_option = config.get_main_option("my_important_option")


def get_metadata():
    if hasattr(target_db, 'metadatas'):
        return target_db.metadatas[None]
    return target_db.metadata


def run_migrations_offline():
    """Запуск миграций в «офлайн»-режиме.

    В этом режиме Alembic работает только с URL подключения,
    без создания Engine. Это полезно там, где нет драйвера БД.
    Все операции выводятся как SQL-текст через context.execute().
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=get_metadata(), literal_binds=True
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Запуск миграций в «онлайн»-режиме.

    Здесь создаётся Engine, открывается соединение и
    миграции выполняются непосредственно в базе данных.
    """

    # Колбэк, который предотвращает создание «пустых» миграций,
    # когда изменения в схеме не обнаружены.
    # Документация: http://alembic.zzzcomputing.com/en/latest/cookbook.html
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('No changes in schema detected.')

    conf_args = current_app.extensions['migrate'].configure_args

    # Включаем безопасную автогенерацию на SQLite и игнорируем вспомогательные
    # таблицы (например, 'user_club'), которыми управляет код вне моделей ORM.
    def include_object(object, name, type_, reflected, compare_to):
        if type_ == 'table' and name in {'user_club'}:
            return False
        if type_ == 'index' and name in {'ix_user_club_user', 'ix_user_club_club'}:
            return False
        return True
    conf_args.setdefault('include_object', include_object)
    if conf_args.get("process_revision_directives") is None:
        conf_args["process_revision_directives"] = process_revision_directives

    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **conf_args
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
