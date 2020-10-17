import abc

from .exception_handling import TestFailure
from .common import test_reuslt_msg_template, hard_fail_msg_template

from .sql.operations import FetchQueryResults
from .csv.operations import get_csv_document, apply_reducer


class Operations(object):
    def __init__(self, logger, test):
        self.logger = logger
        self.test = test

    @staticmethod
    def parse_dict_param(param, column):
        if isinstance(param, dict):
            value = param.get(column)
        else:
            value = param
        return value

    @staticmethod
    def format_test_result_msgs(test_outcomes, test_descriptions):
        test_outcomes_ = test_outcomes.copy()
        for column in test_outcomes_:
            description = test_descriptions.get(column)
            if description is None:
                description = test_descriptions.get("no_column")
            test_outcome = test_outcomes_[column]
            result = test_outcome["result"]
            measure = test_outcome["measure"]
            threshold = test_outcome["threshold"]

            result_template = test_reuslt_msg_template()
            result_message = result_template.format(description=description, result=result, measure=measure,
                                                    threshold=threshold)
            test_outcome["result_msg"] = result_message
        return test_outcomes_

    def build_test_outcomes(self, measure_values):
        test_outcomes = {}
        threshold = self.test.threshold
        predicate = self.test.predicate
        for column in measure_values:
            threshold_ = self.parse_dict_param(threshold, column)
            measure_value = measure_values[column]
            test_result = predicate(measure_value, threshold_)
            test_outcomes[column] = {"result": test_result, "measure": measure_value, "threshold": threshold_}
        return test_outcomes

    def log_test_results(self, test_results):
        for column in test_results:
            test_result = test_results[column]
            result_msg = test_result["result_msg"]
            self.logger(result_msg)
        return True

    def raise_execpetion_if_fail(self, test_results):
        hard_fail = self.test.hard_fail
        for column in test_results:
            test_result = test_results[column]
            hard_fail_ = self.parse_dict_param(hard_fail, column)
            if hard_fail_ is True:
                outcome = test_result["result"]
                if outcome == "test_fail":
                    result_msg = test_result["result_msg"]
                    error_msg_template = hard_fail_msg_template()
                    error_msg = error_msg_template.format(result_msg=result_msg)
                    raise TestFailure(error_msg)
        return True

    @abc.abstractmethod
    def format_test_description(self, *args, **kwargs): pass

    @abc.abstractmethod
    def calculate_measure_values(self): pass

    def execute(self):
        descriptions = self.format_test_description()

        measure_values = self.calculate_measure_values()
        test_outcomes = self.build_test_outcomes(measure_values)
        test_results = self.format_test_result_msgs(test_outcomes, descriptions)

        self.log_test_results(test_results)
        self.raise_execpetion_if_fail(test_results)

        return test_results


class SQLOperations(Operations):
    def __init__(self, conn, logger, test):
        super().__init__(logger, test)
        self.conn = conn

    def format_test_description(self, **description_kwargs):
        descriptions = {}
        description_template = self.test.description
        threshold = self.test.threshold
        measure = self.test.measure
        columns = measure.columns
        from_ = measure.from_
        description_kwargs["from_"] = from_
        for column in columns:
            threshold_ = self.parse_dict_param(threshold, column)
            description_kwargs["threshold"] = threshold_
            description_kwargs["column"] = column
            description = description_template.format(**description_kwargs)
            descriptions[column] = description
        return descriptions

    def calculate_measure_values(self):
        measure = self.test.measure
        query = measure.query
        measure_values = FetchQueryResults(self.conn, query).get_results()
        return measure_values


class SQLSetOperations(SQLOperations):
    def __init__(self, conn, logger, test):
        super().__init__(conn, logger, test)

    def format_test_description(self, **description_kwargs):
        descriptions = {}
        description_template = self.test.description
        threshold = self.test.threshold
        description_kwargs["threshold"] = threshold
        measure = self.test.measure
        columns = measure.columns
        columns_ = ",".join(columns)
        description_kwargs["column"] = columns_
        from_ = measure.from_
        description_kwargs["from_"] = from_
        description = description_template.format(**description_kwargs)
        descriptions[columns_] = description
        return descriptions


class CSVOperations(Operations):
    def __init__(self, logger, test, fieldnames=None, **reducer_kwargs):
        super().__init__(logger, test)
        self.fieldnames = fieldnames
        self.reducer_kwargs = reducer_kwargs

    def format_test_description(self, **description_kwargs):
        descriptions = {}
        description_template = self.test.description
        threshold = self.test.threshold
        measure = self.test.measure
        columns = measure.columns
        from_ = measure.from_
        description_kwargs["from_"] = from_
        for column in columns:
            threshold_ = self.parse_dict_param(threshold, column)
            description_kwargs["threshold"] = threshold_
            description_kwargs["column"] = column
            description = description_template.format(**description_kwargs)
            descriptions[column] = description
        return descriptions

    def calculate_measure_values(self):
        measure = self.test.measure
        delimiter = measure.delimiter
        path = measure.from_
        reducer = measure.reducer
        columns = measure.columns
        document = get_csv_document(path, delimiter=delimiter, fieldnames=self.fieldnames)
        reducer_results = apply_reducer(document, reducer, *columns, **self.reducer_kwargs)
        measure_values = self.build_measure_proportion_values(reducer_results)
        return measure_values

    @staticmethod
    def build_measure_proportion_values(results):
        measure_values = {}
        rowcnt = results["rowcnt"]
        if rowcnt == 0:
            raise ValueError(f"rowcnt must be greater than 0.")

        accum = results["accum"]
        for column in accum:
            result = accum[column]
            measure_value = result / rowcnt
            measure_values[column] = measure_value

        return measure_values


class CSVSetOperations(CSVOperations):
    def __init__(self, logger, test, fieldnames=None, **reducer_kwargs):
        super().__init__(logger, test, fieldnames=fieldnames, **reducer_kwargs)

    def format_test_description(self, **description_kwargs):
        descriptions = {}
        description_template = self.test.description
        threshold = self.test.threshold
        description_kwargs["threshold"] = threshold
        measure = self.test.measure
        columns = measure.columns
        columns_ = ",".join(columns)
        description_kwargs["column"] = columns_
        from_ = measure.from_
        description_kwargs["from_"] = from_
        description = description_template.format(**description_kwargs)
        descriptions[columns_] = description
        return descriptions


class CustomSQLOperations(Operations):
    def __init__(self, conn, logger, test, **test_desc_kwargs):
        super().__init__(logger, test)
        self.conn = conn
        self.test_desc_kwargs = test_desc_kwargs

    def calculate_measure_values(self): pass

    def format_test_description(self, **kwargs):
        test_descriptions = {}
        description_template = self.test.description
        columns = self.test.columns
        threshold = self.test.threshold

        if columns:
            for column in columns:
                threshold_ = self.parse_dict_param(threshold, column)
                kwargs["threshold"] = threshold_
                kwargs["column"] = column
                description = description_template.format(**kwargs)
                test_descriptions[column] = description
        else:
            description = description_template.format(**kwargs)
            test_descriptions["no_column"] = description

        return test_descriptions

    def calcualte_test_results(self):
        def format_test_outcome(outcome):
            measure = outcome.get("measure")
            threshold = outcome.get("threshold")
            result = outcome["result"]
            return {"result": result, "measure": measure, "threshold": threshold}

        test_outcomes = {}
        query = self.test.test
        columns = self.test.columns
        threshold = self.test.threshold

        if columns:
            for column in columns:
                threshold_ = self.parse_dict_param(threshold, column)
                query_ = query.format(column=column, threshold=threshold_)
                test_outcome = FetchQueryResults(self.conn, query_).get_results()
                test_outcomes[column] = format_test_outcome(test_outcome)
        else:
            test_outcome = FetchQueryResults(self.conn, query).get_results()
            column = test_outcome.get("column")
            if column:
                test_outcomes[column] = format_test_outcome(test_outcome)
            else:
                test_outcomes["no_column"] = format_test_outcome(test_outcome)
        return test_outcomes

    def execute(self):
        descriptions = self.format_test_description(**self.test_desc_kwargs)

        test_outcomes = self.calcualte_test_results()

        test_results = self.format_test_result_msgs(test_outcomes, descriptions)

        self.log_test_results(test_results)
        self.raise_execpetion_if_fail(test_results)

        return test_results
