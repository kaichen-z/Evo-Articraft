"""把 20 个案例 prompt 中字面声明的部件关系写入 specs（替换 part_relations）。

抽取纪律：
- 只收 prompt 字面声明的静态关系；每条带原文引句（source 字段）。
- 纯静态措辞 → source 前缀 "prompt:"；由 hinged to / joined by / mounted on 等
  连接措辞得到的 attached_to → 前缀 "prompt-kinematic:"（可区分统计）。
- 主语/宾语绑定不到 link 的照样保留（geom 名兜底或 unmeasurable），
  这是零件粒度缺口的诚实记录。
- 运动学句子（rotates/slides on ...）本身不产生关系声明，归 P3。
"""

import json
import pathlib

SPECS = pathlib.Path(__file__).parent / "specs"

R = {
# ---------------------------------------------------------------- 抽屉柜
"rec_drawer_cabinet_with_sliding_drawers_34d51b44ab674f52b838d4bc4e126590": [
    dict(subject="drawer", relation="inside", object="body",
         source='prompt: "All six drawers slide ... within the rigid outer carcass"'),
],
# ---------------------------------------------------------------- 伸缩臂
"rec_telescoping_boom_73c354e91fd74e1c8f4d08af5836cb4d": [
    dict(subject="outer_tube", relation="supported_by", object="root_housing",
         source='prompt: "A broad root housing supports nested rectangular tubes"'),
    dict(subject="middle_tube", relation="inside", object="outer_tube",
         source='prompt: "nested rectangular tubes"'),
    dict(subject="inner_tube", relation="inside", object="middle_tube",
         source='prompt: "nested rectangular tubes"'),
],
# ---------------------------------------------------------------- 台钳 (子部件绑定缺口演示)
"rec_bench_vise_with_prismatic_jaw_0002": [
    dict(subject="guide_rod", relation="through", object="jaw",
         source='prompt: "parallel guide rod running through the jaw"'),
    dict(subject="fixed_block", relation="below", object="bench",
         source='prompt: "a fixed block below the bench edge"'),
],
# ---------------------------------------------------------------- 收银机
"rec_cash_register_a90a3eb4ec5a49c79034bac363111f2a": [
    dict(subject="screen", relation="attached_to", object="screen_swivel",
         source='prompt: "a rear operator screen on a swivel mount"'),
    *[dict(subject=s, relation="attached_to", object="console_panel",
           source='prompt: "the keys sit in clear rows across the control face"')
      for s in ("menu_key_0", "menu_key_1",
                "number_key_0", "number_key_1", "number_key_2", "number_key_3")],
],
# ---------------------------------------------------------------- 园门
"rec_garden_gate_3ffbd3e876a142d2ab5693140093a96a": [
    dict(subject="latch_leaf", relation="attached_to", object="fixed_frame",
         source='prompt-kinematic: "Each leaf is hinged to an outer post"'),
    dict(subject="bolt_leaf", relation="attached_to", object="fixed_frame",
         source='prompt-kinematic: "Each leaf is hinged to an outer post"'),
    dict(subject="latch_lever", relation="supported_by", object="latch_leaf",
         source='prompt: "one meeting stile carries a latch"'),
    dict(subject="cane_bolt", relation="supported_by", object="bolt_leaf",
         source='prompt: "the other carries a vertical cane bolt"'),
    dict(subject="cane_bolt", relation="through", object="bolt_leaf",
         source='prompt: "the cane bolt clipped through its guide loops on the meeting stile"'),
],
# ---------------------------------------------------------------- 电柜门
"rec_electrical_cabinet_door_5c93513f9fd14694ac2eca6a39c6a4fd": [
    dict(subject="front_door", relation="attached_to", object="cabinet",
         source='prompt-kinematic: "a hinged front door ... on two revolute hinge knuckles"'),
    dict(subject="instrument_panel", relation="attached_to", object="cabinet",
         source='prompt-kinematic: "an inner hinged instrument panel on a revolute hinge"（挂靠对象原文未名, 按关节父件绑定）'),
],
# ---------------------------------------------------------------- 垃圾桶
"rec_wheelie_bin_with_hinged_lid_4cb061e3d69c4d4c843a9b332ee19f03": [
    dict(subject="lid", relation="supported_by", object="bin_body",
         source='prompt: "Lid swing and wheel rolling should both be clearly supported"（支撑者按关节父件绑定）'),
    dict(subject="left_wheel", relation="supported_by", object="rear_axle",
         source='prompt: "Lid swing and wheel rolling should both be clearly supported"（支撑者按关节父件绑定）'),
    dict(subject="right_wheel", relation="supported_by", object="rear_axle",
         source='prompt: "Lid swing and wheel rolling should both be clearly supported"（支撑者按关节父件绑定）'),
],
# ---------------------------------------------------------------- 翻盖手机
"rec_flip_phone_83b0fac634af42e2bd288f59133e70c8": [
    dict(subject="upper_body", relation="attached_to", object="lower_body",
         source='prompt-kinematic: "lower keypad body and a matching upper display body joined by a dual-barrel hinge"'),
],
# ---------------------------------------------------------------- 眼镜
"rec_glasses_9bb2f7b74f5d40548747d32fd306be52": [
    dict(subject="left_temple", relation="supported_by", object="front_frame",
         source='prompt: "each outer corner carries a slender temple arm"'),
    dict(subject="right_temple", relation="supported_by", object="front_frame",
         source='prompt: "each outer corner carries a slender temple arm"'),
],
# ---------------------------------------------------------------- 贴合式家电
"rec_panini_press_with_clamshell_lid_1e6c986dda874fd6a176cd1becc0658d": [
    dict(subject="lid", relation="attached_to", object="base",
         source='prompt-kinematic: "The lid rotates open on a rear horizontal revolute hinge"'),
    dict(subject="thermostat_knob", relation="attached_to", object="base",
         source='prompt: "a thermostat knob rotates continuously on a short side-face shaft"（轴在 base 侧面）'),
],
# ---------------------------------------------------------------- 塔扇
"rec_tower_fan_with_rotary_controls_c23bcbc7114b484290d573db335cd72d": [
    dict(subject="speed_knob", relation="supported_by", object="tower",
         source='prompt: "a top control deck carrying rotary knobs"（deck⊂tower）'),
    dict(subject="timer_knob", relation="supported_by", object="tower",
         source='prompt: "a top control deck carrying rotary knobs"（deck⊂tower）'),
    dict(subject="tower", relation="above", object="base",
         source='prompt: "oscillates on a vertical revolute joint above the base"'),
    dict(subject="blower", relation="inside", object="tower",
         source='prompt: "the internal blower wheel"'),
],
# ---------------------------------------------------------------- 风力机
"rec_wind_turbine_e10650a329fb4c79b8baeee1fa7b8566": [
    dict(subject="nacelle", relation="attached_to", object="tower",
         source='prompt: "The nacelle stays clearly mounted on a yaw bearing at the tower top"'),
    dict(subject="nacelle", relation="above", object="tower",
         source='prompt: "at the tower top"'),
],
# ---------------------------------------------------------------- 转盘
"rec_lazy_susan_efcb4237eb1c4f96a46d0b370cf1dcb5": [
    dict(subject="lower_tier", relation="supported_by", object="central_post",
         source='prompt: "Each circular shelf is carried by its own bearing collar around the post"'),
    dict(subject="upper_tier", relation="supported_by", object="central_post",
         source='prompt: "Each circular shelf is carried by its own bearing collar around the post"'),
    dict(subject="lower_tier", relation="around", object="central_post",
         source='prompt: "bearing collar around the post"（collar⊂tier）'),
    dict(subject="upper_tier", relation="around", object="central_post",
         source='prompt: "bearing collar around the post"（collar⊂tier）'),
],
# ---------------------------------------------------------------- 水轮
"rec_undershot_waterwheel_0003": [
    dict(subject="wheel", relation="supported_by", object="frame",
         source='prompt: "rotary stages should sit on believable hubs, spindles, or bearing collars with clear support"'),
],
# ---------------------------------------------------------------- 办公椅
"rec_office_chair_0004": [
    dict(subject="seat_assembly", relation="above", object="base",
         source='prompt: "The seat sits above a central pedestal"（seat/pedestal 分别⊂两 link）'),
    dict(subject="left_arm_pad", relation="symmetric", object="right_arm_pad",
         source='prompt: "paired armrests flank the seat"（geom 级子部件引用）'),
    dict(subject="wheel", relation="attached_to", object="base",
         source='prompt: "The caster wheels rotate continuously on their axles"（axle⊂base）'),
],
# ---------------------------------------------------------------- 显示器支架
"rec_monitor_mount_c10308ed1ba241a9a835032150c14cbb": [
    dict(subject="first_arm", relation="supported_by", object="mast_clamp",
         source='prompt: "A fixed mast clamp carries a first arm, a second arm, and a compact monitor plate"（后两件为串链传递, 只测直接件）'),
],
# ---------------------------------------------------------------- 三自由度腕
"rec_yawpitchroll_wrist_71a3903167694d5ab1a72ebd73fa28f6": [
    dict(subject="pitch_yoke", relation="between", objects=["yaw_collar", "roll_spindle"],
         source='prompt: "a yaw collar at the root, a pitch yoke in the middle, and a short roll spindle ... at the nose"'),
],
# ---------------------------------------------------------------- 指骨链
"rec_fingerlike_phalanx_chain_4f7c64ddc97c4e75920f166c8615df5f": [
    dict(subject="middle_link", relation="between", objects=["root_knuckle", "distal_link"],
         source='prompt: "a thick root knuckle, a tapered middle link, a short distal link"'),
],
# ---------------------------------------------------------------- 洗碗机
"rec_dishwasher_with_dropdown_door_and_sliding_racks_9dd15c0aefb940f2acd9fd2596b80ced": [
    dict(subject="rocker_0", relation="supported_by", object="control_pod",
         source='prompt: "a short front control pod carrying two rocker switches and a timer knob"'),
    dict(subject="rocker_1", relation="supported_by", object="control_pod",
         source='prompt: "a short front control pod carrying two rocker switches and a timer knob"'),
    dict(subject="timer_knob", relation="supported_by", object="control_pod",
         source='prompt: "a short front control pod carrying two rocker switches and a timer knob"'),
    dict(subject="lower_rack", relation="supported_by", object="body",
         source='prompt: "both racks slide prismatically on supported guides"（guides⊂body）'),
    dict(subject="upper_rack", relation="supported_by", object="body",
         source='prompt: "both racks slide prismatically on supported guides"（guides⊂body）'),
    dict(subject="lower_wash_arm", relation="inside", object="body",
         source='prompt: "wash arms rotate continuously on vertical hubs in the chamber"'),
    dict(subject="upper_wash_arm", relation="inside", object="body",
         source='prompt: "wash arms rotate continuously on vertical hubs in the chamber"'),
    dict(subject="detergent_flap", relation="attached_to", object="door",
         source='prompt: "the detergent flap on the inner door"'),
],
# ---------------------------------------------------------------- 打印机
"rec_all_in_one_printer_with_scanner_lid_and_paper_tray_401e9042a65b4e4c84b3193175918b05": [
    dict(subject="cassette", relation="inside", object="body",
         source='prompt: "the paper cassette slides prismatically from the lower body"'),
    dict(subject="selector_dial", relation="attached_to", object="control_panel",
         source='prompt: "A selector dial at one side of the panel"'),
    dict(subject="flatbed_lid", relation="attached_to", object="body",
         source='prompt-kinematic: "The flatbed lid rotates upward on a rear hinge"'),
    dict(subject="adf_lid", relation="attached_to", object="flatbed_lid",
         source='prompt-kinematic: "the ADF lid rotates on a top hinge"（挂靠对象按关节父件绑定）'),
    dict(subject="control_panel", relation="attached_to", object="body",
         source='prompt-kinematic: "a tilting front touchscreen panel ... tilts on a short horizontal pivot"'),
],
}

n_total = 0
for rid, claims in R.items():
    p = SPECS / f"{rid}.json"
    spec = json.loads(p.read_text(encoding="utf-8"))
    spec["part_relations"] = claims
    spec["_relations_note"] = "仅含 prompt 字面声明的关系(手工抽取, 每条带原文引句); 推测声明已移除"
    p.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    n_total += len(claims)
    print(f"{rid[:48]:<48} {len(claims)} 条")

print(f"\n共写入 {n_total} 条 prompt 声明关系, 覆盖 {len(R)} 个案例")
