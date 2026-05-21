import datetime
import json
import logging

import azure.functions as func

from src.run_ingestion import execute_ingestion

app = func.FunctionApp()


@app.timer_trigger(schedule="0 15 7 * * *", arg_name="my_timer", run_on_startup=False, use_monitor=True)
def ingest_published_statistics(my_timer: func.TimerRequest) -> None:
    if my_timer.past_due:
        logging.info("Timer trigger is running late.")

    logging.info("Published statistics ingestion started at %s", datetime.datetime.utcnow().isoformat())
    result = execute_ingestion()
    logging.info("Ingestion completed: %s", json.dumps(result))
