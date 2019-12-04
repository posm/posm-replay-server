from replay_tool.models import ReplayTool

import logging


def set_error_status_on_exception(prev_status=None, curr_status=None):
    """ This automatically checks for previous status of replay tool and sets status
    and errorred values depending on if exception occurred or not
    """
    # TODO: check if env vars are set
    logger = logging.getLogger(curr_status)

    def decorator(f):
        def wrapper(*args, **kwargs):
            replay_tool, _ = ReplayTool.objects.get_or_create()
            if replay_tool.errorred is True:
                raise Exception(f'Relay tool has errorred while {replay_tool.status}')

            if replay_tool.status != prev_status or not replay_tool.current_state_completed:
                raise Exception(f'Current AOI extract can be run only after {prev_status} is completed')

            replay_tool.status = curr_status
            replay_tool.current_state_completed = False
            replay_tool.save()

            try:
                f(*args, **kwargs)
                replay_tool.current_state_completed = True
                replay_tool.save()
                return True
            except Exception:
                replay_tool.errorred = True
                replay_tool.save()
                logger.error(f'Error during {curr_status}', exc_info=True)
                import traceback
                print(traceback.format_exc())
                print(f'Error during {curr_status}')
                return False
        return wrapper
    return decorator
