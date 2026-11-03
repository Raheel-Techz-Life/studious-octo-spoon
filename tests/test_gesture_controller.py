from core.event_logger import EventLogger
from core.gesture_controller import GestureController


def test_mapped_gesture_executes_handler():
    logger = EventLogger()
    controller = GestureController(logger, mapping={"Thumb_Up": "confirm"})
    calls = []
    controller.register_handler("confirm", lambda: calls.append("confirm"))

    result = controller.handle("Thumb_Up")

    assert result.status == "executed"
    assert result.command == "confirm"
    assert calls == ["confirm"]
    assert logger.all()[0].status == "executed"


def test_unmapped_gesture_is_reported_unmapped():
    logger = EventLogger()
    controller = GestureController(logger, mapping={})

    result = controller.handle("Pointing_Up")

    assert result.status == "unmapped"
    assert result.command is None
    assert logger.all() == []  # nothing recorded for an unmapped gesture


def test_disabled_controller_blocks_execution_without_calling_handler():
    logger = EventLogger()
    controller = GestureController(logger, mapping={"Victory": "next"})
    calls = []
    controller.register_handler("next", lambda: calls.append("next"))
    controller.set_enabled(False)

    result = controller.handle("Victory")

    assert result.status == "blocked"
    assert calls == []  # handler must not run while disabled
    assert logger.all()[0].status == "blocked"


def test_remap_changes_target_command():
    logger = EventLogger()
    controller = GestureController(logger, mapping={"Victory": "next"})
    controller.remap("Victory", "back")

    result = controller.handle("Victory")

    assert result.command == "back"


def test_event_logger_is_bounded():
    logger = EventLogger(max_events=3)
    for i in range(5):
        logger.record(f"g{i}", "cmd")

    events = logger.all()
    assert len(events) == 3
    assert events[0].gesture == "g4"  # most recent first
