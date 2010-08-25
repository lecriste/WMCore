#!/usr/bin/env python
"""
_New_

Oracle implementation of Locations.New
"""

from WMCore.WMBS.MySQL.Locations.New import New as NewLocationMySQL

class New(NewLocationMySQL):    
    sql = """INSERT INTO wmbs_location (id, site_name, job_slots) SELECT
             wmbs_location_SEQ.nextval, :location, :slots AS site_name FROM DUAL
             WHERE NOT EXISTS (SELECT site_name FROM wmbs_location
             WHERE site_name = :location)"""
