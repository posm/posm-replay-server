from replay_tool.models import ReplayTool

import logging


def set_error_status_on_exception(prev_state=None, curr_state=None):
    """ This automatically checks for previous status of replay tool and sets status
    and errored values depending on if exception occurred or not
    """
    # TODO: check if env vars are set
    logger = logging.getLogger(curr_state)

    def decorator(f):
        def wrapper(*args, **kwargs):
            replay_tool, _ = ReplayTool.objects.get_or_create()
            if replay_tool.has_errored is True:
                raise Exception(f'Relay tool has errored while {replay_tool.state}')

            if replay_tool.state != prev_state or not replay_tool.is_current_state_complete:
                raise Exception(f'Current AOI extract can be run only after {prev_state} is completed')

            replay_tool.state = curr_state
            replay_tool.is_current_state_complete = False
            replay_tool.save()

            try:
                f(*args, **kwargs)
                replay_tool.is_current_state_complete = True
                replay_tool.save()
                return True
            except Exception:
                replay_tool.has_errored = True
                replay_tool.save()
                logger.error(f'Error during {curr_state}', exc_info=True)
                import traceback
                print(traceback.format_exc())
                print(f'Error during {curr_state}')
                return False
        return wrapper
    return decorator
