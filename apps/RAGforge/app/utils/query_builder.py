from typing import Type

from sqlalchemy import ColumnElement
from sqlalchemy.sql.expression import and_

from app.models import BaseModel

SQLALCHEMY_QUERY_MAPPER = {
    "eq": "__eq__",
    "ne": "__ne__",
    "lt": "__lt__",
    "lte": "__le__",
    "gt": "__gt__",
    "gte": "__ge__",
}


def dict_to_sqlalchemy_query(
        model, filter_options
) -> ColumnElement[bool]:
    """
    Convert a dictionary of filter options to SQLAlchemy query filters.

    Args:
        model (Type[BaseModel]): The SQLAlchemy model class.
        filter_options (dict): A dictionary containing filter options.

    Returns:
        tuple: A tuple of SQLAlchemy filter expressions.
    """
    filters = []
    copied_dict = filter_options.copy()
    for key in filter_options:
        attr = getattr(model, key, None)
        if attr is None:
            continue
        option_from_dict = copied_dict.pop(key)
        if type(option_from_dict) in [int, float]:
            filters.append(attr == option_from_dict)
        elif type(option_from_dict) in [str]:
            filters.append(attr.like("%" + option_from_dict + "%"))
        elif type(option_from_dict) in [bool]:
            filters.append(attr.is_(option_from_dict))

    for custom_option in copied_dict:
        if "__" not in custom_option:
            continue
        key, command = custom_option.split("__")
        attr = getattr(model, key, None)
        if attr is None:
            continue
        option_from_dict = copied_dict[custom_option]
        if command == "in":
            filters.append(attr.in_([option.strip() for option in option_from_dict.split(",")]))
        elif command in SQLALCHEMY_QUERY_MAPPER.keys():
            filters.append(getattr(attr, SQLALCHEMY_QUERY_MAPPER[command])(option_from_dict))
        elif command == "isnull":
            bool_command = "__eq__" if option_from_dict else "__ne__"
            filters.append(getattr(attr, bool_command)(None))

    return and_(True, *filters)
