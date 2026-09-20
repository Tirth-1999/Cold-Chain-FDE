Select count(*) from dbo.TBL_SC_FLEET_HIST_RAW;

SELECT TOP 2 Latitude, Longitude, Current_Temperature_C FROM FDE_VIEWS.VW_ACTIVE_FLEET

CREATE TABLE FDE_VIEWS.AgentAuditLog (
    LogID INT IDENTITY(1,1) PRIMARY KEY,
    Timestamp DATETIME DEFAULT GETDATE(),
    SessionID VARCHAR(50),
    NodeExecuted VARCHAR(50),
    ToolName VARCHAR(100),
    Content NVARCHAR(MAX) -- NVARCHAR to safely handle JSON strings and large LLM outputs
);
GRANT INSERT ON FDE_VIEWS.AgentAuditLog TO USR_FDE_RO;