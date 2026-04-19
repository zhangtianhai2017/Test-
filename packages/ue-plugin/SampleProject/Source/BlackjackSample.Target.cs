using UnrealBuildTool;
using System.Collections.Generic;

public class BlackjackSampleTarget : TargetRules
{
    public BlackjackSampleTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.V4;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("BlackjackSample");
    }
}
