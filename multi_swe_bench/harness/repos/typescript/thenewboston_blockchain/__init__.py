import os
from multi_swe_bench.harness.instance import Instance
from .base import ThenewbostonWebsiteInstance

# Dynamic registration of thenewboston-blockchain instances
# This replaces the 41 redundant files and static imports

# List of all website_[PR]_to_[ISSUE] identifiers
# These were extracted from the previous static implementation
INSTANCES = [
    "website_1383_to_1373", "website_1384_to_1372", "website_1390_to_1371",
    "website_1391_to_1352", "website_1392_to_1345", "website_1395_to_1382",
    "website_1398_to_1381", "website_1400_to_1339", "website_1401_to_1348",
    "website_1403_to_1375", "website_1405_to_1362", "website_1412_to_1363",
    "website_1413_to_1350", "website_1415_to_1354", "website_1416_to_1355",
    "website_1417_to_1299", "website_1419_to_1361", "website_1421_to_1347",
    "website_1424_to_1380", "website_1426_to_1359", "website_1427_to_1377",
    "website_1431_to_1336", "website_1443_to_1360", "website_1448_to_1337",
    "website_1449_to_1340", "website_1450_to_1379", "website_1452_to_1367",
    "website_1455_to_1364", "website_1456_to_1376", "website_1458_to_1341",
    "website_1460_to_1447", "website_1461_to_1342", "website_1466_to_1351",
    "website_1469_to_1344", "website_1482_to_1480", "website_1496_to_1368",
    "website_1515_to_1343", "website_1518_to_1349", "website_1519_to_1378"
]

for instance_id in INSTANCES:
    Instance.register("thenewboston-blockchain", instance_id)(ThenewbostonWebsiteInstance)
