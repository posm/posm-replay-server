#!/bin/bash -x

# Create a pipe to read
# Delete if already exists
rm osmosis_command_reader.fifo 2>/dev/null
mkfifo osmosis_command_reader.fifo


while true
do
    while read cmd
    do
        $cmd 2> /tmp/command_reader_error;
        # Write to another named pipe 'osmosis_result_reader' which is created by python app
        # NOTE: the following outputs multiline errors into single, which is desired
        # at the moment
	errcode=$?
	if [[ $errcode -ne 0 ]]; then
           errmsg=`cat /tmp/command_reader_error`
        else
	   errmsg="no errrors reported"
        fi
        echo "$? $errmsg" >> osmosis_result_reader.fifo
    done < osmosis_command_reader.fifo
done
