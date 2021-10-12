from datetime import date, timedelta
import os

from dotenv import find_dotenv, load_dotenv
import requests

# Load local .env
env_path: str = find_dotenv()
load_dotenv(env_path)

NEO_API_BASE_URL: str = "https://api.nasa.gov/neo/rest/v1/feed"
SPLUNK_HOST_NAME: str = os.getenv("SPLUNK_HOST_NAME")
NASA_API_KEY: str = os.getenv("NASA_API_KEY")
HEC_TOKEN: str = os.getenv("HEC_TOKEN")


def build_neo_url(api_key: str, start_dt: date, end_dt: date) -> str:
    """
    Build the Near Earth Objects (NEOs) API URL

    Args:
        api_key (str): User-specified NASA API key
        start_dt (date): Starting date for asteroid search
        end_dt (date): Ending date for asteroid search. Must be within 0 and 7 days of
            start_dt

    Raises:
        ValueError: When end_dt is not within 0 and 7 days of start_dt

    Returns:
        str: The NEO API URL for the supplied date range
    """
    # end_dt must be 0-7 days after start_dt
    if not (0 <= (end_dt - start_dt).days <= 7):
        raise ValueError(
            "The NASA NEO Feed API documentation indicates that end date must be within"
            " 0 and 7 days of the start date."
        )

    return (
        f"{NEO_API_BASE_URL}?start_date={start_dt.strftime('%Y-%m-%d')}"
        f"&end_date={end_dt.strftime('%Y-%m-%d')}&detailed=true&api_key={api_key}"
    )


def pull_neo_feed(url: str) -> dict:
    """
    Pull Near Earth Objects (NEOs) from NASA's NEO Feed

    Args:
        url (str): NEO API URL

    Returns:
        dict: All NEOs from the specified API URL
    """

    get_response: requests.Response = requests.get(url=url)
    json_data: dict = get_response.json()
    return json_data["near_earth_objects"]


def split_neo_dict(neo_dict: dict) -> list:
    """
    Convert NEO dictionary into a list of NEOs

    Args:
        neo_dict (dict): NEO dictionary pulled from NEO feed

    Returns:
        [list]: List of NEOs
    """
    return [i for v in neo_dict.items() for i in v]


def build_hec_uri(
    host_name: str,
    port: str = "443",
    end_point: str = "services/collector",
    protocol: str = "https",
    trial_version: bool = False,
) -> str:
    """
    Build the Splunk HEC URI

    Args:
        host_name (str): Splunk Cloud instance that runs HEC
        port (str, optional): HEC Port Number. Overrides to 8088 if trial_version is
            True. Defaults to "443".
        end_point (str, optional): HEC endpoint to use. Defaults to
            "services/collector".
        protocol (str, optional): Must be "https" or "http". Defaults to "https".
        trial_version (bool, optional): Using free trial version of Splunk Cloud.
            Defaults to True.

    Returns:
        str: [description]
    """
    if protocol not in ["https", "http"]:
        raise ValueError("protocol must be 'https' or 'http'")

    if trial_version:
        host_type: str = "inputs."
        port = "8088"
    else:
        host_type = "http-inputs-"

    return f"{protocol}://{host_type}{host_name}:{port}/{end_point}"


def post_to_hec(
    hec_uri: str, hec_token: str, index: str, data: dict
) -> requests.Response:
    """
    Upload data to selected index via HEC

    Args:
        hec_uri (str): HEC URI
        hec_token (str): HEC token
        index (str): Index to upload to
        data (dict): Data to upload

    Returns:
        requests.Response: HTTP response for uploading to Splunk via HEC
    """
    headers = {"Authorization": f"Splunk {hec_token}"}
    hec_json = {"sourcetype": "_json", "index": index, "event": data}

    return requests.post(hec_uri, json=hec_json, headers=headers, verify=False)


def main() -> None:
    """Pull NASA Near-Earth-Object JSON data and post to Splunk Cloud using HEC"""

    hec_uri: str = build_hec_uri(host_name=SPLUNK_HOST_NAME, trial_version=True)

    min_dt: date = date.fromisoformat("2020-01-01")
    max_dt: date = date.fromisoformat("2020-12-31")
    delta: timedelta = timedelta(days=7)

    while min_dt <= max_dt:
        # Ensure end_dt in NEO URL doesn't exceed max_dt from above
        _max_dt: date = min(min_dt + delta, max_dt)

        neo_url: str = build_neo_url(
            api_key=NASA_API_KEY, start_dt=min_dt, end_dt=_max_dt
        )
        neo_dict: dict = pull_neo_feed(url=neo_url)
        neo_list: list = split_neo_dict(neo_dict=neo_dict)

        for x in neo_list:
            post_request: requests.Response = post_to_hec(
                hec_uri=hec_uri, hec_token=HEC_TOKEN, index="nasa_neo", data=x
            )
            status_cd: int = post_request.status_code

            if status_cd == 200:
                print("Succesfully uploaded via HEC")
            else:
                print(f"Failed to upload via HEC with status code {status_cd}")

        min_dt = _max_dt + timedelta(days=1)


if __name__ == "__main__":
    main()
