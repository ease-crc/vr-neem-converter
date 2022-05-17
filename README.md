# VR NEEM Converter

## Manual adaptions to VR NEEM dumps

1. Add
```owl
<!ENTITY srdl2-cap "http://knowrob.org/kb/srdl2-cap.owl#">
<!ENTITY srdl2-comp "http://knowrob.org/kb/srdl2-comp.owl#">
```
to the `<!DOCTYPE rdf:RDF[` section of the semantic map
2. Add
```owl
xmlns:srdl2-cap="http://knowrob.org/kb/srdl2-cap.owl#"
xmlns:srdl2-comp="http://knowrob.org/kb/srdl2-comp.owl#"
```
to the `<rdf:RDF` section of the semantic map
3. Replace
```owl
<owl:imports rdf:resource="package://knowrob/owl/knowrob.owl"/>
```
with
```owl
<owl:imports rdf:resource="http://knowrob.org/kb/knowrob.owl"/>
```
in all OWL files

## Configuring the NEEM converter

## Converting a VR NEEM

1. Make sure ROS is running: `roscore`
```
