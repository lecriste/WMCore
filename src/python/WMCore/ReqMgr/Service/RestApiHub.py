"""
Module defines REST API methods and their handles.
Implementation of handles is in corresponding modules, not here.

"""
from __future__ import print_function, division

import cherrypy

from WMCore.Configuration import Configuration
from WMCore.REST.Server import RESTApi
from WMCore.REST.Services import ProcessMatrix

from WMCore.ReqMgr.ReqMgrCouch import ReqMgrCouch
from WMCore.ReqMgr.Service.Auxiliary import (Info, ReqMgrConfigData, PermissionsConfig,
                                CMSSWVersions, WMAgentConfig, CampaignConfig, UnifiedConfig)
from WMCore.ReqMgr.Service.RequestAdditionalInfo import (RequestSpec,
    WorkloadConfig, WorkloadSplitting)
from WMCore.ReqMgr.Service.Request import Request, RequestStatus, RequestType
from WMCore.ReqMgr.Service.WMStatsInfo import WMStatsInfo


class IndividualCouchManager(object):
    """
    Wrapper for the database API object, such that it's *not* shared
    among all the Rest APIs.
    """

    def __init__(self, config):
        self.db_handler = ReqMgrCouch(config)


class RestApiHub(RESTApi):
    """
    Server object for REST data access API.
    """

    def __init__(self, app, config, mount):
        """
        :arg app: reference to application object; passed to all entities.
        :arg config: reference to configuration; passed to all entities.
        :arg str mount: API URL mount point; passed to all entities."""

        RESTApi.__init__(self, app, config, mount)

        cherrypy.log("ReqMgr entire configuration:\n%s" % Configuration.getInstance())
        cherrypy.log("ReqMgr REST hub configuration subset:\n%s" % config)

        # Makes raw format as default
        # self.formats.insert(0, ('application/raw', RawFormat()))
        self._add({"about": Info(app, IndividualCouchManager(config), config, mount),
                   "info": Info(app, IndividualCouchManager(config), config, mount),
                   "app_config": ReqMgrConfigData(app, IndividualCouchManager(config), config, mount),
                   "request": Request(app, IndividualCouchManager(config), config, mount),
                   "cmsswversions": CMSSWVersions(app, IndividualCouchManager(config), config, mount),
                   "wmagentconfig": WMAgentConfig(app, IndividualCouchManager(config), config, mount),
                   "permissions": PermissionsConfig(app, IndividualCouchManager(config), config, mount),
                   "campaignconfig": WMAgentConfig(app, IndividualCouchManager(config), config, mount),
                   "unifiedconfig": UnifiedConfig(app, IndividualCouchManager(config), config, mount),
                   "status": RequestStatus(app, IndividualCouchManager(config), config, mount),
                   "type": RequestType(app, IndividualCouchManager(config), config, mount),
                   "spec_template": RequestSpec(app, IndividualCouchManager(config), config, mount),
                   "workload_config": WorkloadConfig(app, IndividualCouchManager(config), config, mount),
                   "splitting": WorkloadSplitting(app, IndividualCouchManager(config), config, mount),
                   "wmstats_info": WMStatsInfo(app, IndividualCouchManager(config), config, mount),
                   "proc_status": ProcessMatrix(app, self, config, mount)
                  })
