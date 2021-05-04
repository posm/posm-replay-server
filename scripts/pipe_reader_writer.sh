#!/bin/bash

# Create a pipe to read
# Delete if already exists
rm /tmp/osmosis_command/command_reader.fifo 2>/dev/null
mkfifo /tmp/osmosis_command/command_reader.fifo

rm /tmp/osmosis_command/result_reader.fifo 2>/dev/null
mkfifo /tmp/osmosis_command/result_reader.fifo


while true
do
    while read cmd
    do
        $cmd 2> /tmp/osmosis_command/command_reader_error;
        # Write to another named pipe '/tmp/osmosis_command/result_reader.fifo' which is created by python app
        # NOTE: the following outputs multiline errors into single, which is desired
        # at the moment
        errcode=$?
        if [[ $errcode -ne 0 ]]; then
            errmsg=`cat /tmp/osmosis_command/command_reader_error`
        else
            errmsg="no errrors reported"
        fi
        echo "$? $errmsg" >> /tmp/osmosis_command/result_reader.fifo
    done < /tmp/osmosis_command/command_reader.fifo
    sleep 1
done
