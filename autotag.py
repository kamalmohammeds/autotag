import os
import re
import fnmatch
import sqlite3
from traceback import format_exc
import yaml
import logging

class GenerateTags:
    def __init__(self, filename):
        self.filename = filename
        self.testid = filename.split('_')[0]

    def _parse_coverity_report(self):
        try:
            with open('./coverage_report/'+self.filename, 'r') as cov_report_fp:
                line_list = cov_report_fp.readlines()
        except Exception as err:
            print('Bail out with exception {}'.format(err))
            return None

        func_list = []
        line_cov_list = []
        cov_dict = {}
        for line in line_list:
            func = re.findall("Function '(.*)'", line)
            file_hit = re.findall("File '(.*)'", line)
            line_cov = re.findall("Lines executed:(.*)%", line)
            if func:
                func_list += func
            if line_cov:
                line_cov_list += line_cov
            if file_hit:
                file_hit = [f.split('/')[-1:][0].strip() for f in file_hit]
                cov_dict[file_hit[0]] = {'Functions': func_list, 'Line Coverage':line_cov_list}
                func_list = []
                line_cov_list = []

        return cov_dict

    def _filter_coverage_report(self, min_tag_weight=0.01, max_tag_weight=100.00):
        with open('./coverage_report/'+self.filename,'r+') as coverage_report:
            cov_lines = list(filter(lambda x: x != '\n', coverage_report.readlines()))
            coverage_report.seek(0)
            for line,line_ahead in zip(cov_lines,cov_lines[1:]):
                cov_per_line = re.findall('([0-9.]+)%',line)
                cov_per_line_ahead = re.findall('([0-9.]+)%',line_ahead)

                if cov_per_line:
                    cov_per_line = float(cov_per_line[0])
                else:
                    cov_per_line = 100.00

                if cov_per_line_ahead:
                    cov_per_line_ahead = float(cov_per_line_ahead[0])
                else:
                    cov_per_line_ahead = 0.00

                if (cov_per_line >= min_tag_weight and cov_per_line <= max_tag_weight) and (cov_per_line_ahead >= min_tag_weight and cov_per_line_ahead <= max_tag_weight) and 'No executable lines' not in line and 'No executable lines' not in line_ahead:
                    coverage_report.write(line)
            coverage_report.truncate()

    def generate_tags(self):
        '''
        Include all gcov activities

        '''
        self._filter_coverage_report()
        tag_dict = self._parse_coverity_report()
        #tag_list = [ (', '+k.split('.')[0]+'_').join(v['Functions']) for k,v in tag_dict.items()]
        #returns only filename for demo
        #print tag_dict.items()
        return tag_dict.keys()


###How to log and need I have to use TestResultError for raising exceptions
class GenerateTagfile:
    def __init__(self):
        """
        Create db connection object and create table in db if it does not exists
        """
        self.connection = sqlite3.connect("/home/kmohammed/autotagging.db")
        self.cursor = self.connection.cursor()
        self.log = logging.Logger()
        if self.connection:
            try:
                sql_create_tasks_table = """CREATE TABLE IF NOT EXISTS tasks (
                                       test_case_id text PRIMARY KEY,
                                       test_file_path text NOT NULL,
                                       yaml_file_path text NOT NULL
                                   );"""
                self.cursor.execute(sql_create_tasks_table)
            except Exception as err:
                print('Bailing out with exception {}'.format(err))
                exc_lines = format_exc().splitlines()
                for line in exc_lines:
                    self.log.error(line)
        else:
            self.log.error("Connection not available to SQL db - autotagging.db")

    def write_into_db(self, test_list, test_file_path, yaml_file_path):
        """
        Build a repository of test_case_id, test script file path, yaml file path
        """
        if self.connection:
            try:
                sql_insert_tasks_table = ''' INSERT OR REPLACE INTO tasks(test_case_id, test_file_path, yaml_file_path)
                                         VALUES(?,?,?) '''
                for test_case_id in test_list:
                    self.cursor.execute(sql_insert_tasks_table, (test_case_id, test_file_path, yaml_file_path))
                    self.connection.commit()
            except Exception as err:
                print('Bailing out with exception {}'.format(err))
                exc_lines = format_exc().splitlines()
                for line in exc_lines:
                    self.log.error(line)
        else:
            self.log.error("Connection not available to SQL db - autotagging.db")

    def create_yaml_dict(self):
        """
        Create yaml file for all test scripts
        """
        for root, _, filenames in os.walk("/home/kmohammed/Gigascripts/Testscripts/EmbeddedQA/TD/Resilient_weighted_hashing/POC/"):
            for filename in fnmatch.filter(filenames, '*.py'):
                if filename != '__init__.py':
                    try:
                        with open(os.path.join(root, filename), "rt") as filehandler:
                            file_path = os.path.join(root, filename)
                            data = filehandler.read()
                            tag_list = re.findall("@GTSTestcase\(tags=[\"'](.*?)[\"']", data)
                            tag_list = [s+' ~' for s in tag_list]
                            if tag_list:
                                test_list = re.findall('def test_C(.*)\(', data)
                                test_list = ['tags_C'+s for s in test_list]
                                if test_list and len(test_list) == len(tag_list):
                                    yaml_file = 'tags_'+filename.split('.py')[0]+'.yaml'
                                    yaml_dict = dict(zip(test_list, tag_list))
                                    yaml_abs_file = os.path.join(root, yaml_file)
                                    if not os.path.isfile(yaml_abs_file):
                                        with open(yaml_abs_file, "w+") as file_ptr:
                                            dump_yaml = yaml.dump(yaml_dict, file_ptr)
                                    self.write_into_db(test_list, file_path, yaml_abs_file)
                    except Exception as err:
                        print('Bailing out with exception {}'.format(err))
                        exc_lines = format_exc().splitlines()
                        for line in exc_lines:
                            self.log.error(line)

    def add_tags_yaml(self, test_case_id, tag):
        """
        Add tags for corresponding testcase
        """
        if self.connection:
            try:
                test_case_id = 'tags_'+test_case_id
                self.cursor.execute("SELECT * FROM tasks WHERE test_case_id=?", (test_case_id,))
                row = self.cursor.fetchall()
                if row:
                    #test_file_path = row[0][1]
                    yaml_file_path = row[0][2]
                    tags = ' '.join(tag)
                    with open(yaml_file_path, "rw+") as file_ptr:
                        cfg = yaml.load(file_ptr)
                        cfg[test_case_id] = cfg[test_case_id].split('~')[0]+'~ '+tags
                        '''
                        with open(yaml_file_path,"rw+") as file_ptr:
                            cfg = yaml.load(file_ptr)

                            for tg in tags:
                            if tg not in cfg[test_case_id]:
                                cfg[test_case_id] = cfg[test_case_id]+' '+tg
                        '''
                        print(cfg)
                        file_ptr.seek(0)
                        yaml.dump(cfg, file_ptr, default_style='>', default_flow_style=False)

                else:
                    self.log.error("Test case info {} not available in database".format(test_case_id))
            except Exception as err:
                print('Bailing out with exception {}'.format(err))
                exc_lines = format_exc().splitlines()
                for line in exc_lines:
                    self.log.error(line)
        else:
            self.log.error("Connection not available to SQL db - autotagging.db")

if __name__ == '__main__':
    gen_tag_file = GenerateTagfile()
    gen_tag_file.create_yaml_dict()
    coverage_files = os.walk('./coverage_report')
    for root, _, filenames in coverage_files:
        pass
    for filename in filenames:
        testcase_id = filename.split('_')[0]
        gen_tag = GenerateTags(filename)
        gen_tag_file.add_tags_yaml(testcase_id, gen_tag.generate_tags())
