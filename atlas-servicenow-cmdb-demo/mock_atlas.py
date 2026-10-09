import json
from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "inventory.json"


def load_fixture(path: Path = FIXTURE_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class MockAtlasClient:
    def __init__(self, path: Path = FIXTURE_PATH):
        self.data = load_fixture(path)
        self._clusters_by_project = {}
        for cluster in self.data["clusters"]:
            self._clusters_by_project.setdefault(cluster["groupId"], []).append(cluster)
        self._processes_by_project = {}
        for process in self.data["processes"]:
            self._processes_by_project.setdefault(process["groupId"], []).append(process)

    def get_organization(self) -> dict:
        return self.data["organization"]

    def iter_projects(self):
        yield from self.data["projects"]

    def iter_clusters(self, project_id: str):
        yield from self._clusters_by_project.get(project_id, [])

    def iter_processes(self, project_id: str):
        yield from self._processes_by_project.get(project_id, [])
