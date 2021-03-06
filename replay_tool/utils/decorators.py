from replay_tool.models import ReplayTool
import traceback

import logging


def set_error_status_on_exception(prev_state=None, curr_state=None):
    """ This automatically checks for previous status of replay tool and sets status
    and errored values depending on if exception occurred or not
    """
    logger = logging.getLogger(curr_state)

    def decorator(f):
        def wrapper(*args, **kwargs):
            replay_tool, _ = ReplayTool.objects.get_or_create()
            wipe_error = True
            if replay_tool.has_errored is True:
                wipe_error = False
                raise Exception(f'Relay tool has errored while {replay_tool.state}')

            if replay_tool.state != prev_state or not replay_tool.is_current_state_complete:
                err_msg = f'{curr_state} can be run only after {prev_state} is completed'
                raise Exception(err_msg)

            replay_tool.state = curr_state
            replay_tool.is_current_state_complete = False
            replay_tool.save()

            try:
                ret = f(*args, **kwargs)
                replay_tool = ReplayTool.objects.get()
                replay_tool.is_current_state_complete = True
                replay_tool.save()
                return ret
            except Exception as e:
                replay_tool = ReplayTool.objects.get()
                replay_tool.has_errored = True
                if wipe_error:
                    replay_tool.error_details = f'{e.args[0]}: \n\n {traceback.format_exc()}'
                replay_tool.save()
                logger.error(f'Error during {curr_state}', exc_info=True)
                return None
        return wrapper
    return decorator
