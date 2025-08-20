from refactored_classes import Cell, Module, Panel, String
from simple_calc import _get_cell_conditions, _get_voltage_from_current, _calculate_voltage, _get_bypass_current
import random 

# Helper to randomly shade a fraction of all cells in the string
def shade_cells(string_obj, fraction=0.2):
    all_cells = [cell for panel in string_obj.panel_list for cell in panel._all_cells()]
    num_to_shade = int(len(all_cells) * fraction)
    for cell in random.sample(all_cells, num_to_shade):
        cell._set_shade(True)

'''
@func regression testing of these functions
@params none
@output text saying if functions correct
'''
def regression_testing():
    Iph_cell, Is_cell, nVth_cell, Rs_cell, Rp_cell = _get_cell_conditions('Jinko_Solar_Co___Ltd_JKM410M_72HL_V', 1000, 25)
    print("Test 1 - _get_cell_conditions - irr=1000, T-25")
    print(f"Iph_cell={Iph_cell:.6g}, Is_cell={Is_cell:.6g}, nVth_cell={nVth_cell:.6g}, Rs_cell={Rs_cell:.6g}, Rp_cell={Rp_cell:.6g}")
    print(f'\n')

    Iph_cell, Is_cell, nVth_cell, Rs_cell, Rp_cell = _get_cell_conditions('Jinko_Solar_Co___Ltd_JKM410M_72HL_V', 100, 25)
    print("Test 2 - _get_cell_conditions - irr=100, T-25")
    print(f"Iph_cell={Iph_cell:.6g}, Is_cell={Is_cell:.6g}, nVth_cell={nVth_cell:.6g}, Rs_cell={Rs_cell:.6g}, Rp_cell={Rp_cell:.6g}")
    print(f'\n')

    voltage = _get_voltage_from_current('Jinko_Solar_Co___Ltd_JKM410M_72HL_V', 1000, 25, 10)
    print("Test 3 = _get_voltage_from_current - irr=1000, temp=25, current=10")
    print(f'Voltage is {voltage}')
    print(f'Panel voltage is {voltage*144} and power is {voltage*144*10}')
    print(f'\n')

    voltage = _get_voltage_from_current('Jinko_Solar_Co___Ltd_JKM410M_72HL_V', 1000, 25, 5)
    print("Test 4 = _get_voltage_from_current - irr=1000, temp=25, current=5")
    print(f'Voltage is {voltage} - voltage is higher')
    print(f'Panel voltage is {voltage*144} and power is {voltage*144*5}')
    print(f'\n')

    voltage = _get_voltage_from_current('Jinko_Solar_Co___Ltd_JKM410M_72HL_V', 100, 25, 10)
    print("Test 5 = _get_voltage_from_current - irr=100, temp=25, current=10")
    print(f'Voltage is {voltage} - voltage should be negative')
    print(f'Panel voltage is {voltage*144} and power is {voltage*144*10}')
    print(f'\n')

    voltage = _get_voltage_from_current('Jinko_Solar_Co___Ltd_JKM410M_72HL_V', 100, 25, 1)
    print("Test 6 = _get_voltage_from_current - irr=100, temp=25, current=1")
    print(f'Voltage is {voltage} - voltage should be positive')
    print(f'Panel voltage is {voltage*144} and power is {voltage*144*1}')
    print(f'\n')
    
    voltage = _get_voltage_from_current('Jinko_Solar_Co___Ltd_JKM410M_72HL_V', -50, 25, 1)
    print("Test 7 = _get_voltage_from_current - irr=-50, temp=25, current=1")
    print(f'Voltage is {voltage} - just testing for solving negative irr')
    print(f'Panel voltage is {voltage*144} and power is {voltage*144*1}')
    print(f'\n')

    shaded_voltage = _get_voltage_from_current('Jinko_Solar_Co___Ltd_JKM410M_72HL_V', 100, 25, 10)
    unshaded_voltage = _get_voltage_from_current('Jinko_Solar_Co___Ltd_JKM410M_72HL_V', 1000, 25, 10)
    print("Test 8 = module._get_voltage - temp=25, current=10, un/shaded G=1000, 100, 12 cells in module")
    module = Module(12)
    total_voltage_1 = module._get_voltage(shaded_voltage, unshaded_voltage)
    module.cell_list[0]._set_shade(True)
    total_voltage_4 = module._get_voltage(shaded_voltage, unshaded_voltage)
    for i in range(6):
        module.cell_list[i]._set_shade(True)
    total_voltage_2 = module._get_voltage(shaded_voltage, unshaded_voltage)
    for i in range(12):
        module.cell_list[i]._set_shade(True)
    total_voltage_3 = module._get_voltage(shaded_voltage, unshaded_voltage)
    print(f'Voltage with no shade is {total_voltage_1} - voltage should be positive')
    print(f'Voltage with 1 cell shaded is {total_voltage_4} - voltage should be 0.7 (bd active)')
    print(f'Voltage with half shade is {total_voltage_2} - voltage should be 0.7 (bd active)')
    print(f'Voltage with full shade is {total_voltage_3} - voltage should be 0.7 (bd active)')
    print(f'\n')

    print("Test 9-13 = panel._get_voltage - same values as above, 12 modules")
    # === Test 9 ===
    panel9 = Panel(12, 12)
    voltage9_1 = panel9._get_voltage(shaded_voltage, unshaded_voltage)
    panel9._all_cells()[0]._set_shade(True)
    voltage9_2 = panel9._get_voltage(shaded_voltage, unshaded_voltage)

    # === Test 10 ===
    panel10 = Panel(12, 12)
    voltage10_1 = panel10._get_voltage(shaded_voltage, unshaded_voltage)
    for i in random.sample(range(len(panel10._all_cells())), 10):
        panel10._all_cells()[i]._set_shade(True)
    voltage10_2 = panel10._get_voltage(shaded_voltage, unshaded_voltage)

    # === Test 11 ===
    panel11 = Panel(12, 12)
    voltage11_1 = panel11._get_voltage(shaded_voltage, unshaded_voltage)
    for m in range(3):  # fully shade 3 modules
        for cell in panel11.module_list[m].cell_list:
            cell._set_shade(True)
    voltage11_2 = panel11._get_voltage(shaded_voltage, unshaded_voltage)

    # === Test 12 ===
    panel12 = Panel(12, 12)
    voltage12_1 = panel12._get_voltage(shaded_voltage, unshaded_voltage)
    for idx, cell in enumerate(panel12._all_cells()):
        if idx % 2 == 0:
            cell._set_shade(True)
    voltage12_2 = panel12._get_voltage(shaded_voltage, unshaded_voltage)

    # === Test 13 ===
    panel13 = Panel(12, 12)
    voltage13_1 = panel13._get_voltage(shaded_voltage, unshaded_voltage)
    for cell in panel13._all_cells():
        cell._set_shade(True)
    # unshade one module (12 cells)
    for cell in panel13.module_list[5].cell_list:
        cell._set_shade(False)
    voltage13_2 = panel13._get_voltage(shaded_voltage, unshaded_voltage)

    # === Print results ===
    print("Test 9 = panel._get_voltage - no shade vs 1 shaded cell")
    print(f'Voltage with no shade is {voltage9_1} - should be positive')
    print(f'Voltage with 1 shaded cell is {voltage9_2} - should be slightly less\n')

    print("Test 10 = panel._get_voltage - random shading of 10 cells")
    print(f'Voltage with no shade is {voltage10_1} - should be positive')
    print(f'Voltage with 10 random shaded cells is {voltage10_2} - should drop\n')

    print("Test 11 = panel._get_voltage - 3 modules fully shaded")
    print(f'Voltage with no shade is {voltage11_1} - should be positive')
    print(f'Voltage with 3 modules shaded is {voltage11_2} - should be much lower\n')

    print("Test 12 = panel._get_voltage - checkerboard shading")
    print(f'Voltage with no shade is {voltage12_1} - should be positive')
    print(f'Voltage with checkerboard shading is {voltage12_2} - intermediate drop\n')

    print("Test 13 = panel._get_voltage - all shaded except 1 module unshaded")
    print(f'Voltage with full shade is {voltage13_1} - should be near bypass diode voltage')
    print(f'Voltage with 1 unshaded module is {voltage13_2} - should recover partially\n')

    # Example string setup
    string1 = String(num_panels=3, num_cells=144, num_modules=12, panel_name='Jinko_Solar_Co___Ltd_JKM410M_72HL_V')

    print("Testing with 3 panels of 12 modules, 144 cell")

    # === Test 14: Full sun, no shading ===
    string1.reset_shade()
    shaded_conditions = (100, 25)
    unshaded_conditions = (1000, 25)
    Pmax14, Vmp14, Imp14 = string1._model_power(shaded_conditions, unshaded_conditions, draw_graph=False)
    print(f"Test 14: No shading")
    print(f"Pmax={Pmax14:.2f}, Vmp={Vmp14:.2f}, Imp={Imp14:.2f}")
    print(f'\n')

    # === Test 15: 20% of cells shaded randomly, mid-irradiance ===
    string1.reset_shade()
    shade_cells(string1, fraction=0.2)
    shaded_conditions = (400, 25)
    unshaded_conditions = (800, 25)
    Pmax15, Vmp15, Imp15 = string1._model_power(shaded_conditions, unshaded_conditions, draw_graph=False)
    print(f"Test 15: 20% shading")
    print(f"Pmax={Pmax15:.2f}, Vmp={Vmp15:.2f}, Imp={Imp15:.2f}")
    print(f'\n')

    # === Test 16: 50% of cells shaded randomly, morning conditions ===
    string1.reset_shade()
    shade_cells(string1, fraction=0.5)
    shaded_conditions = (200, 20)
    unshaded_conditions = (600, 20)
    Pmax16, Vmp16, Imp16 = string1._model_power(shaded_conditions, unshaded_conditions, draw_graph=False)
    print(f"Test 16: 50% shaded")
    print(f"Pmax={Pmax16:.2f}, Vmp={Vmp16:.2f}, Imp={Imp16:.2f}")
    print(f'\n')

    # === Test 17: 80% of cells shaded, evening conditions ===
    string1.reset_shade()
    shade_cells(string1, fraction=0.8)
    shaded_conditions = (50, 25)
    unshaded_conditions = (400, 25)
    Pmax17, Vmp17, Imp17 = string1._model_power(shaded_conditions, unshaded_conditions, draw_graph=False)
    print(f"Test 17: 80% shading")
    print(f"Pmax={Pmax17:.2f}, Vmp={Vmp17:.2f}, Imp={Imp17:.2f}")
    print(f'\n')

    # === Test 18: Random 30% shading, uniform irradiance ===
    string1.reset_shade()
    shade_cells(string1, fraction=0.3)
    shaded_conditions = (500, 25)
    unshaded_conditions = (500, 25)
    Pmax18, Vmp18, Imp18 = string1._model_power(shaded_conditions, unshaded_conditions, draw_graph=False)
    print("Test 18: 30% shaded")
    print(f"Pmax={Pmax18:.2f}, Vmp={Vmp18:.2f}, Imp={Imp18:.2f}")
    print(f'\n')

if __name__ == "__main__":
    regression_testing()