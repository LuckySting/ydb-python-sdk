import functools
from google.protobuf.empty_pb2 import Empty
from . import issues, types, _apis, convert, scheme, operation, _utilities


def bad_session_handler(func):
    @functools.wraps(func)
    def decorator(rpc_state, response_pb, session_state, *args, **kwargs):
        try:
            return func(rpc_state, response_pb, session_state, *args, **kwargs)
        except issues.BadSession:
            session_state.reset()
            raise
    return decorator


@bad_session_handler
def wrap_prepare_query_response(rpc_state, response_pb, session_state, yql_text):
    session_state.complete_query()
    issues._process_response(response_pb.operation)
    message = _apis.ydb_table.PrepareQueryResult()
    response_pb.operation.result.Unpack(message)
    data_query = types.DataQuery(yql_text, message.parameters_types)
    session_state.keep(data_query, message.query_id)
    return data_query


def prepare_request_factory(session_state, yql_text):
    request = session_state.start_query().attach_request(_apis.ydb_table.PrepareDataQueryRequest())
    request.yql_text = yql_text
    return request


class AlterTableOperation(operation.Operation):
    def __init__(self, rpc_state, response_pb, driver):
        super(AlterTableOperation, self).__init__(rpc_state, response_pb, driver)
        self.ready = response_pb.operation.ready


def copy_tables_request_factory(session_state, source_destination_pairs):
    request = session_state.attach_request(_apis.ydb_table.CopyTablesRequest())
    for source_path, destination_path in source_destination_pairs:
        table_item = request.tables.add()
        table_item.source_path = source_path
        table_item.destination_path = destination_path
    return request


def explain_data_query_request_factory(session_state, yql_text):
    request = session_state.start_query().attach_request(_apis.ydb_table.ExplainDataQueryRequest())
    request.yql_text = yql_text
    return request


class _ExplainResponse(object):
    def __init__(self, ast, plan):
        self.query_ast = ast
        self.query_plan = plan


def wrap_explain_response(rpc_state, response_pb, session_state):
    session_state.complete_query()
    issues._process_response(response_pb.operation)
    message = _apis.ydb_table.ExplainQueryResult()
    response_pb.operation.result.Unpack(message)
    return _ExplainResponse(message.query_ast, message.query_plan)


@bad_session_handler
def wrap_execute_scheme_result(rpc_state, response_pb, session_state):
    session_state.complete_query()
    issues._process_response(response_pb.operation)
    message = _apis.ydb_table.ExecuteQueryResult()
    response_pb.operation.result.Unpack(message)
    return convert.ResultSets(message.result_sets)


def execute_scheme_request_factory(session_state, yql_text):
    request = session_state.start_query().attach_request(_apis.ydb_table.ExecuteSchemeQueryRequest())
    request.yql_text = yql_text
    return request


@bad_session_handler
def wrap_describe_table_response(rpc_state, response_pb, sesssion_state, scheme_entry_cls):
    issues._process_response(response_pb.operation)
    message = _apis.ydb_table.DescribeTableResult()
    response_pb.operation.result.Unpack(message)
    return scheme._wrap_scheme_entry(
        message.self,
        scheme_entry_cls,
        message.columns,
        message.primary_key,
        message.shard_key_bounds,
        message.indexes,
        message.table_stats if message.HasField('table_stats') else None,
        message.ttl_settings if message.HasField('ttl_settings') else None,
        message.attributes
    )


def create_table_request_factory(session_state, path, table_description):
    if isinstance(table_description, _apis.ydb_table.CreateTableRequest):
        request = session_state.attach_request(table_description)
        return request
    request = _apis.ydb_table.CreateTableRequest()
    request.path = path
    request.primary_key.extend(list(table_description.primary_key))
    for column in table_description.columns:
        request.columns.add(name=column.name, type=column.type_pb)

    if table_description.profile is not None:
        request.profile.MergeFrom(
            table_description.profile.to_pb(
                table_description
            )
        )

    for index in table_description.indexes:
        request.indexes.add().MergeFrom(
            index.to_pb())

    if table_description.ttl_settings is not None:
        request.ttl_settings.MergeFrom(
            table_description.ttl_settings.to_pb()
        )

    request.attributes.update(table_description.attributes)

    return session_state.attach_request(request)


def keep_alive_request_factory(session_state):
    request = _apis.ydb_table.KeepAliveRequest()
    return session_state.attach_request(request)


@bad_session_handler
def cleanup_session(rpc_state, response_pb, session_state, session):
    issues._process_response(response_pb.operation)
    session_state.reset()
    return session


@bad_session_handler
def initialize_session(rpc_state, response_pb, session_state, session):
    issues._process_response(response_pb.operation)
    message = _apis.ydb_table.CreateSessionResult()
    response_pb.operation.result.Unpack(message)
    session_state.set_id(message.session_id).attach_endpoint(rpc_state.endpoint)
    return session


@bad_session_handler
def wrap_operation(rpc_state, response_pb, session_state, driver=None):
    return operation.Operation(rpc_state, response_pb, driver)


def wrap_operation_bulk_upsert(rpc_state, response_pb, driver=None):
    return operation.Operation(rpc_state, response_pb, driver)


@bad_session_handler
def wrap_keep_alive_response(rpc_state, response_pb, session_state, session):
    issues._process_response(response_pb.operation)
    return session


def describe_table_request_factory(session_state, path, settings=None):
    request = session_state.attach_request(_apis.ydb_table.DescribeTableRequest())
    request.path = path

    if settings is not None and hasattr(settings, 'include_shard_key_bounds') and settings.include_shard_key_bounds:
        request.include_shard_key_bounds = settings.include_shard_key_bounds

    if settings is not None and hasattr(settings, 'include_table_stats') and settings.include_table_stats:
        request.include_table_stats = settings.include_table_stats

    return request


def alter_table_request_factory(
        session_state, path,
        add_columns, drop_columns,
        alter_attributes,
        add_indexes, drop_indexes,
        set_ttl_settings, drop_ttl_settings):
    request = session_state.attach_request(_apis.ydb_table.AlterTableRequest(path=path))
    if add_columns is not None:
        for column in add_columns:
            request.add_columns.add(
                name=column.name, type=column.type_pb
            )

    if drop_columns is not None:
        request.drop_columns.extend(list(drop_columns))

    if drop_indexes is not None:
        request.drop_indexes.extend(list(drop_indexes))

    if add_indexes is not None:
        for index in add_indexes:
            request.add_indexes.add().MergeFrom(index.to_pb())

    if alter_attributes is not None:
        request.alter_attributes.update(alter_attributes)

    if set_ttl_settings is not None:
        request.set_ttl_settings.MergeFrom(set_ttl_settings.to_pb())

    if drop_ttl_settings is not None and drop_ttl_settings:
        request.drop_ttl_settings.MergeFrom(Empty())

    return request


def read_table_request_factory(session_state, path, key_range=None, columns=None, ordered=False, row_limit=None, use_snapshot=None):
    request = _apis.ydb_table.ReadTableRequest()
    request.path = path
    request.ordered = ordered
    if key_range is not None and key_range.from_bound is not None:
        target_attribute = 'greater_or_equal' if key_range.from_bound.is_inclusive() else 'greater'
        getattr(request.key_range, target_attribute).MergeFrom(
            convert.to_typed_value_from_native(
                key_range.from_bound.type,
                key_range.from_bound.value
            )
        )

    if key_range is not None and key_range.to_bound is not None:
        target_attribute = 'less_or_equal' if key_range.to_bound.is_inclusive() else 'less'
        getattr(request.key_range, target_attribute).MergeFrom(
            convert.to_typed_value_from_native(
                key_range.to_bound.type,
                key_range.to_bound.value
            )
        )

    if columns is not None:
        for column in columns:
            request.columns.append(column)
    if row_limit:
        request.row_limit = row_limit
    if use_snapshot is not None:
        if isinstance(use_snapshot, bool):
            if use_snapshot:
                request.use_snapshot = _apis.FeatureFlag.ENABLED
            else:
                request.use_snapshot = _apis.FeatureFlag.DISABLED
        else:
            request.use_snapshot = use_snapshot
    return session_state.attach_request(request)


def bulk_upsert_request_factory(table, rows, column_types):
    request = _apis.ydb_table.BulkUpsertRequest()
    request.table = table
    request.rows.MergeFrom(convert.to_typed_value_from_native(
        types.ListType(column_types).proto,
        rows
    ))
    return request


def wrap_read_table_response(response):
    issues._process_response(response)
    return convert.ResultSet.from_message(response.result.result_set)


class SessionState(object):
    def __init__(self, client_cache_enabled):
        self._session_id = None
        self._query_cache = _utilities.LRUCache(1000)
        self._default = (None, None)
        self._pending_query = False
        self._endpoint = None
        self._client_cache_enabled = client_cache_enabled

    def __contains__(self, query):
        return self.lookup(query) != self._default

    def reset(self):
        self._query_cache = _utilities.LRUCache(1000)
        self._session_id = None
        self._pending_query = False
        self._endpoint = None

    def attach_endpoint(self, endpoint):
        self._endpoint = endpoint
        return self

    @property
    def endpoint(self):
        return self._endpoint

    @property
    def session_id(self):
        return self._session_id

    def pending_query(self):
        return self._pending_query

    def set_id(self, session_id):
        self._session_id = session_id
        return self

    def keep(self, query, query_id):
        if self._client_cache_enabled:
            self._query_cache.put(
                query.name,
                (query, query_id))
        return self

    @staticmethod
    def _query_key(query):
        return query.name if isinstance(query, types.DataQuery) else _utilities.get_query_hash(query)

    def lookup(self, query):
        return self._query_cache.get(self._query_key(query), self._default)

    def erase(self, query):
        query, query_id = self.lookup(query)
        self._query_cache.erase(query.name)

    def complete_query(self):
        self._pending_query = False
        return self

    def start_query(self):
        if self._pending_query:
            # don't invalidate session at this point
            self.reset()
            raise issues.BadSession("Pending previous query completion!")
        self._pending_query = True
        return self

    def attach_request(self, request):
        if self._session_id is None:
            raise issues.BadSession("Empty session_id")
        request.session_id = self._session_id
        return request
