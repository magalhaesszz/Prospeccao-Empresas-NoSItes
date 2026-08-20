from prospector.coverage import CoveragePlanner
def test_grid_is_deterministic_and_unique():
    p=CoveragePlanner(3.5,25);cells=p.all_cells(-16.6869,-49.2648);assert len(cells)==25;assert len({c.key for c in cells})==25;assert cells[0].ring==0
def test_history_prioritizes_unscanned_cells():
    p=CoveragePlanner(3.5,9);cells=p.all_cells(-16.68,-49.26);planned=p.plan(-16.68,-49.26,{cells[0].key:5,cells[1].key:3});assert planned[0].key not in {cells[0].key,cells[1].key};assert planned[-1].key==cells[0].key
