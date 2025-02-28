import logging
import re
from enum import Enum
from typing import Callable


class QueryType(Enum):
    GET = "get"


class SoqlQuery:
    def __init__(self, query: str, sf_object: str, sf_object_fields: list[str], query_type="get"):
        self.sf_object_fields = sf_object_fields
        self.sf_object = sf_object
        self.query = query
        self.query_type = QueryType(query_type)
        self.check_query(self.query)

    def __str__(self) -> str:
        return self.query

    @classmethod
    def build_from_object(cls, sf_object: str, describe_object_method: Callable, query_type="get",
                          fields: list = None) -> 'SoqlQuery':
        sf_object_fields = describe_object_method(sf_object)
        if fields:
            invalid_fields = [field for field in fields if field not in sf_object_fields]
            if invalid_fields:
                raise ValueError(
                    f"The following field(s) are not available for the '{sf_object}' "
                    f"object: {', '.join(invalid_fields)}")
            sf_object_fields = [field for field in fields if field in sf_object_fields]
        query = cls._construct_soql_from_fields(sf_object, sf_object_fields)
        return SoqlQuery(query, sf_object, sf_object_fields, query_type)

    @classmethod
    def build_from_query_string(cls, query_string: str,
                                describe_object_method: Callable, query_type="get") -> 'SoqlQuery':
        SoqlQuery.check_query(query_string)
        sf_object = cls._get_object_from_query(query_string)
        sf_object_fields = describe_object_method(sf_object)
        return SoqlQuery(query_string, sf_object, sf_object_fields, query_type)

    @staticmethod
    def _list_to_lower(str_list: list[str]) -> list[str]:
        return [x.lower() for x in str_list]

    @staticmethod
    def _construct_soql_from_fields(sf_object: str, sf_object_fields: list[str]) -> str:
        soql_query = f"SELECT {','.join(sf_object_fields)} FROM {sf_object}"
        return soql_query

    @staticmethod
    def _get_object_from_query(query):
        # remove strings within brackets
        query_no_brackets = re.sub("\\(.*?\\)", "", query)
        # list words in query
        word_list = query_no_brackets.lower().split()
        # Only 1 from should exist
        from_index = word_list.index("from")
        #  object name is 1 word after the "from"
        object_name = word_list[from_index + 1]
        # remove non alphanumeric from objectname
        object_name = re.sub(r'\W+', '', object_name)
        return object_name

    @staticmethod
    def check_query(query: str) -> None:
        if not isinstance(query, str):
            raise ValueError("SOQL query must be a single string")
        query_words = query.lower().split()
        if "select" not in query_words:
            raise ValueError("SOQL query must contain SELECT")
        if "from" not in query_words:
            raise ValueError("SOQL query must contain FROM")
        if "offset" in query_words:
            raise ValueError("SOQL bulk queries do not support OFFSET clauses")
        if "typeof" in query_words:
            raise ValueError("SOQL bulk queries do not support TYPEOF clauses")

    def set_query_to_incremental(self, incremental_field: str, continue_from_value: str) -> None:
        if incremental_field.lower() in self._list_to_lower(self.sf_object_fields):
            incremental_string = f" WHERE {incremental_field} >= {continue_from_value}"
        else:
            raise ValueError(f"Field {incremental_field} is not present in the {self.sf_object} object ")

        self.query = self._add_to_where_clause(self.query, incremental_string)

    def set_deleted_option_in_query(self, deleted: bool) -> None:
        if not deleted and "isdeleted" in self._list_to_lower(self.sf_object_fields):
            is_deleted_string = " WHERE IsDeleted = false "
            self.query = self._add_to_where_clause(self.query, is_deleted_string)
        elif deleted and "isdeleted" not in self._list_to_lower(self.sf_object_fields):
            logging.warning(f"Waring: IsDeleted is not a field in the {self.sf_object} object, cannot fetch deleted "
                            f"records")

    @staticmethod
    def _add_to_where_clause(soql: str, new_where_string: str) -> str:
        and_string = " and "

        match = re.search(r'\bwhere\b', soql, re.IGNORECASE)

        if match:
            where_location_start = match.start()
            where_location_end = match.end()
            before_where = soql[:where_location_start]
            after_where = soql[where_location_end:]
            new_query = "".join([before_where, new_where_string, and_string, after_where])
        else:
            new_query = "".join([soql, new_where_string])
        return new_query

    def check_pkey_in_query(self, pkeys: list[str]) -> list:
        missing_keys = []
        # split a string by space, comma, and period characters
        query_words = re.split("\\s|(?<!\\d)[,.](?!\\d)", self.query.lower())
        for pkey in pkeys:
            if pkey.lower() not in query_words:
                missing_keys.append(pkey)
        return missing_keys

    def add_limit(self, limit: int = 1) -> None:
        """
        This method adds LIMIT 10 clause to the SOQL query.
        """
        if "limit" not in self.query.lower():
            self.query = self.query + f" LIMIT {limit}"
        else:
            logging.warning("The SOQL query already contains a LIMIT clause. Ignoring add_limit request.")
