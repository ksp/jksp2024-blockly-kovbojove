from dataclasses import dataclass
from datetime import datetime
import sys
import dateutil.parser
import json
import os

from .blocks import bullet_factories, cowboy_factories
from .exceptions import ProgramParseException
from .parser import Parser
from .program import Program, nop_program

data_dir = "data"


@dataclass
class TeamProgram:
    name: str
    description: str
    last_modified: datetime
    program: Program


class Team:
    login: str
    password: str

    cowboy_programs: dict[str, TeamProgram]
    active_cowboy: str | None = None

    bullet_programs: dict[str, TeamProgram]
    active_bullet: str | None = None

    def __init__(self, login: str, password: str, load_from_file: bool = True) -> None:
        self.login = login
        self.password = password

        self.cowboy_programs = {}
        self.bullet_programs = {}

        if load_from_file:
            if not os.path.isfile(self._team_filename()):
                return

            with open(self._team_filename()) as f:
                data = json.load(f)

            self.cowboy_programs, self.active_cowboy = self._load(
                "cowboy", Parser(cowboy_factories),
                data.get("cowboy_programs", []), data.get("active_cowboy"))

            self.bullet_programs, self.active_bullet = self._load(
                "bullet", Parser(bullet_factories),
                data.get("bullet_programs", []), data.get("active_bullet"))

    def _team_filename(self):
        return f"{data_dir}/team_{self.login}.json"

    def _program_filename(self, filename_prefix: str, uuid: str):
        return f"{data_dir}/{filename_prefix}_{self.login}_{uuid}.xml"

    def _load(self, filename_prefix: str, parser: Parser, records: list[dict[str, str]], active: str | None):
        programs: dict[str, TeamProgram] = {}
        for record in records:
            uuid = record["uuid"]
            name = record["name"]
            description = record["description"]
            last_modified = dateutil.parser.parse(record["last_modified"])

            filename = self._program_filename(filename_prefix, uuid)
            if not os.path.exists(filename):
                continue
            with open(filename) as f:
                xml_input = f.read()
            try:
                program = parser.parse_program(xml_input)
            except ProgramParseException as e:
                print(f"WARN: Program {filename} not runnable: {e}", file=sys.stderr)
                program = Program(None, None, xml_input)

            programs[uuid] = TeamProgram(
                name=name, description=description,
                last_modified=last_modified, program=program)

        if active and active in programs:
            if not programs[active].program.valid():
                print(f"ERROR: Active program {active} is not runnable")
                return programs, None
            return programs, active
        else:
            return programs, None

    def _save(self):
        data = {
            "cowboy_programs": [
                {
                    "uuid": uuid,
                    "name": info.name,
                    "description": info.description,
                    "last_modified": info.last_modified.strftime("%Y-%m-%d %H:%M:%S"),
                } for (uuid, info) in self.cowboy_programs.items()
            ],
            "active_cowboy": self.active_cowboy,
            "bullet_programs": [
                {
                    "uuid": uuid,
                    "name": info.name,
                    "description": info.description,
                    "last_modified": info.last_modified.strftime("%Y-%m-%d %H:%M:%S"),
                } for (uuid, info) in self.bullet_programs.items()
            ],
            "active_bullet": self.active_bullet,
        }
        with open(self._team_filename(), "w") as f:
            json.dump(data, f, indent=4)

    def save_cowboy(self, uuid: str, name: str, description: str, program: Program) -> TeamProgram:
        cowboy = TeamProgram(
            name=name, description=description, last_modified=datetime.now(),
            program=program)
        self.cowboy_programs[uuid] = cowboy

        with open(self._program_filename("cowboy", uuid), "w") as f:
            f.write(program.raw_xml)

        if self.active_cowboy is None and program.valid():
            self.active_cowboy = uuid
        self._save()

        return cowboy

    def delete_cowboy(self, uuid: str) -> None:
        if uuid not in self.cowboy_programs or uuid == self.active_cowboy:
            return
        os.remove(self._program_filename("cowboy", uuid))
        del self.cowboy_programs[uuid]
        self._save()

    def set_active_cowboy(self, uuid: str) -> bool:
        if uuid in self.cowboy_programs and self.cowboy_programs[uuid].program.valid():
            self.active_cowboy = uuid
            self._save()
            return True
        return False

    def get_cowboy_program(self) -> Program:
        if self.active_cowboy:
            program = self.cowboy_programs[self.active_cowboy].program
            if program.valid():
                return program
        return nop_program

    def save_bullet(self, uuid: str, name: str, description: str, program: Program) -> TeamProgram:
        bullet = TeamProgram(
            name=name, description=description, last_modified=datetime.now(),
            program=program)
        self.bullet_programs[uuid] = bullet

        with open(self._program_filename("bullet", uuid), "w") as f:
            f.write(program.raw_xml)

        if self.active_bullet is None and program.valid():
            self.active_bullet = uuid
        self._save()

        return bullet

    def delete_bullet(self, uuid: str) -> None:
        if uuid not in self.bullet_programs or uuid == self.active_bullet:
            return
        os.remove(self._program_filename("bullet", uuid))
        del self.bullet_programs[uuid]
        self._save()

    def set_active_bullet(self, uuid: str) -> bool:
        if uuid in self.bullet_programs and self.bullet_programs[uuid].program.valid():
            self.active_bullet = uuid
            self._save()
            return True
        return False

    def get_bullet_program(self) -> Program:
        if self.active_bullet:
            program = self.bullet_programs[self.active_bullet].program
            if program.valid():
                return program
        return nop_program
