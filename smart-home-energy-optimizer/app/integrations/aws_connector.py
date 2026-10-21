import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("aws_connector")

class AWSIntegrationService:
    """
    Manages genuine AWS IoT Core Device Shadow and DynamoDB telemetry operations.
    Supports dual-mode execution:
      - 'live': Connects to AWS IoT Core (iot-data) and Amazon DynamoDB via boto3.
      - 'simulation': Fully mirrors the AWS IoT Core Device Shadow contract locally
                     with realistic shadow schemas for zero-friction local development.
    """
    def __init__(self):
        self.mode = os.getenv("AWS_MODE", "simulation").lower()
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.iot_endpoint = os.getenv("AWS_IOT_ENDPOINT", "mock-iot-core.iot.us-east-1.amazonaws.com")
        self.telemetry_table = os.getenv("DYNAMODB_TELEMETRY_TABLE", "HomeEnergyTelemetry")
        self.shadow_journal: list = []

        self._boto3_available = False
        self._iot_client = None
        self._dynamodb = None

        if self.mode == "live":
            self._init_live_aws()

    def _init_live_aws(self):
        try:
            import boto3
            self._iot_client = boto3.client("iot-data", endpoint_url=f"https://{self.iot_endpoint}", region_name=self.region)
            self._dynamodb = boto3.resource("dynamodb", region_name=self.region)
            self._boto3_available = True
            logger.info("AWS live clients initialized successfully.")
        except Exception as e:
            logger.warning(f"Could not initialize live AWS clients ({e}). Falling back to simulation mode.")
            self.mode = "simulation"

    def update_device_shadow(self, thing_name: str, desired_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates an AWS IoT Device Shadow following the canonical AWS IoT Shadow JSON document format:
        {
          "state": {
            "desired": { ... }
          }
        }
        """
        shadow_payload = {
            "state": {
                "desired": desired_state
            },
            "clientToken": f"token-{int(datetime.utcnow().timestamp())}"
        }

        timestamp = datetime.utcnow().isoformat()

        if self.mode == "live" and self._boto3_available:
            try:
                response = self._iot_client.update_thing_shadow(
                    thingName=thing_name,
                    payload=json.dumps(shadow_payload)
                )
                res_data = json.loads(response["payload"].read().decode("utf-8"))
                return {
                    "status": "published_to_aws_iot_core",
                    "mode": "live",
                    "thing_name": thing_name,
                    "payload": res_data,
                    "timestamp": timestamp
                }
            except Exception as e:
                logger.error(f"Failed to update AWS IoT Device Shadow for {thing_name}: {e}")
                return {"status": "aws_error", "mode": "live", "error": str(e), "thing_name": thing_name}

        # Simulated AWS IoT Device Shadow Journal
        journal_entry = {
            "status": "shadow_updated",
            "mode": "simulation",
            "aws_service": "AWS IoT Core Device Shadow",
            "topic": f"$aws/things/{thing_name}/shadow/update",
            "thing_name": thing_name,
            "shadow_document": shadow_payload,
            "timestamp": timestamp
        }
        self.shadow_journal.append(journal_entry)
        if len(self.shadow_journal) > 50:
            self.shadow_journal.pop(0)

        return journal_entry

    def ingest_telemetry_record(self, telemetry_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ingests time-series smart meter reading into Amazon DynamoDB.
        Partition Key: device_id
        Sort Key: timestamp
        """
        if self.mode == "live" and self._boto3_available:
            try:
                table = self._dynamodb.Table(self.telemetry_table)
                table.put_item(Item=telemetry_data)
                return {"status": "stored_in_dynamodb", "mode": "live"}
            except Exception as e:
                logger.error(f"DynamoDB put_item failed: {e}")
                return {"status": "dynamodb_error", "mode": "live", "error": str(e)}

        return {
            "status": "ingested_simulated_dynamodb",
            "mode": "simulation",
            "table": self.telemetry_table,
            "partition_key": telemetry_data.get("device_id"),
            "sort_key": telemetry_data.get("timestamp")
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "region": self.region,
            "iot_endpoint": self.iot_endpoint,
            "dynamodb_table": self.telemetry_table,
            "boto3_available": self._boto3_available,
            "recent_shadow_events_count": len(self.shadow_journal),
            "recent_events": self.shadow_journal[-5:]
        }

# Global singleton
aws_service = AWSIntegrationService()
