from typing import List, Dict, Any, Optional, Literal
from src.database.models import Filter

OperatorType = Literal[
    "==",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    "in",
    "not in",
    "is",
    "is not",
    "like",
    "ilike",
    "between",
    "not between",
]


class QueryParser:
    """
    Parse complex query parameters into Filter objects.

    Supports various formats:
    - Simple: ?field=value
    - With operator: ?field__operator=value
    - Multiple values: ?field__in=value1,value2,value3
    - Complex: ?field__between=10,20
    """

    SUPPORTED_OPERATORS: List[OperatorType] = list(OperatorType.__args__)

    @classmethod
    def parse_query_params(
        cls, query_params: Dict[str, Any], allowed_fields: Optional[List[str]] = None
    ) -> List[Filter]:
        """
        Parse query parameters into Filter objects.

        Args:
            query_params: Dictionary of query parameters
            allowed_fields: List of allowed field names for security

        Returns:
            List of Filter objects
        """
        filters: List[Filter] = []

        for key, value in query_params.items():
            if key in ["filters", "page", "size", "sort_by", "sort_order", "search"]:
                continue

            if value is None or value == "":
                continue

            parsed_filters = cls._parse_single_param(key, value, allowed_fields)
            filters.extend(parsed_filters)

        return filters

    @classmethod
    def _parse_single_param(
        cls, key: str, value: Any, allowed_fields: Optional[List[str]] = None
    ) -> List[Filter]:
        """Parse a single query parameter into Filter objects."""
        filters: List[Filter] = []

        if "__" in key:
            field, operator_str = key.split("__", 1)
        else:
            field, operator_str = key, "=="

        if allowed_fields and field not in allowed_fields:
            return []

        if operator_str not in cls.SUPPORTED_OPERATORS:
            return []

        operator: OperatorType = operator_str  # type: ignore

        parsed_value = cls._parse_value(value, operator)

        if parsed_value is not None:
            filters.append(Filter(field=field, operator=operator, value=parsed_value))

        return filters

    @classmethod
    def _parse_value(cls, value: Any, operator: OperatorType) -> Any:
        """Parse value based on the operator type."""
        if value is None:
            return None

        if isinstance(value, str):
            if operator in ["in", "not in"]:
                return [v.strip() for v in value.split(",") if v.strip()]

            elif operator in ["between", "not between"]:
                parts = [v.strip() for v in value.split(",")]
                if len(parts) == 2:
                    try:
                        return [float(p) if "." in p else int(p) for p in parts]
                    except ValueError:
                        return parts
                return None

            elif value.lower() in ["true", "false"]:
                return value.lower() == "true"

            elif value.lower() in ["null", "none"]:
                return None

            else:
                try:
                    return float(value) if "." in value else int(value)
                except ValueError:
                    return value

        return value


def parse_filters(
    query_params: Dict[str, Any], allowed_fields: List[str]
) -> List[Filter]:
    """Parse query parameters specifically for user filtering."""

    return QueryParser.parse_query_params(query_params, allowed_fields)


def build_search_filters(search_term: str, fields: List[str]) -> List[Filter]:
    """Build filters for searching across multiple fields."""
    if not search_term or not fields:
        return []

    return [
        Filter(field=field, operator="ilike", value=f"%{search_term}%")
        for field in fields
    ]
